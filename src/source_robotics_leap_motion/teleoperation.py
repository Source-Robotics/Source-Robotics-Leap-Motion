"""Synchronous orchestration of latest-mode tracking and an explicit robot adapter."""

from __future__ import annotations

from ._compat import Self
from .adapters.base import RobotAdapter
from .control import TeleoperationController, TeleoperationStatus
from .control_config import TeleoperationConfig
from .control_models import PoseTarget, RobotFeedback
from .errors import (
    AdapterError,
    ConnectionError,
    StaleFrameError,
    TeleoperationError,
    TrackingTimeoutError,
)
from .models import Frame
from .tracker import Tracker


class Teleoperator:
    """Owns the robot adapter; the caller owns the surrounding Tracker context.

    Call arm explicitly, then step from one application thread. Adapter operations
    are synchronous and must be bounded. Controller-side command expiry is required
    to handle loss of this application or its network connection.
    """

    def __init__(
        self, tracker: Tracker, *, robot: RobotAdapter, config: TeleoperationConfig
    ) -> None:
        self.tracker, self.robot, self.config = tracker, robot, config
        self.controller = TeleoperationController(config)
        self._opened = False
        self._disconnected = False
        self.last_frame: Frame | None = None

    @property
    def status(self) -> TeleoperationStatus:
        return self.controller.status

    def __enter__(self) -> Self:
        if self._opened:
            raise TeleoperationError("Teleoperator is already open")
        if self.tracker.health.status == "closed" or self.tracker.health.mode != "latest":
            raise TeleoperationError("Open a latest-mode Tracker before the Teleoperator")
        if self.tracker.max_frame_age > self.config.max_frame_age:
            raise TeleoperationError("Tracker max_frame_age must not exceed the control age limit")
        capabilities = self.robot.capabilities
        if not capabilities.cartesian_position:
            raise TeleoperationError(
                "Adapter must accept Cartesian positions; supply kinematics there"
            )
        if self.config.control_orientation and not capabilities.orientation:
            raise TeleoperationError("Adapter does not support configured orientation control")
        if self.config.gripper is not None and not capabilities.gripper:
            raise TeleoperationError("Adapter does not support configured gripper control")
        self.controller = TeleoperationController(self.config)
        self._disconnected = False
        self.last_frame = None
        try:
            self._call("open")
            self._opened = True
            self._call("hold", "disarmed")
        except BaseException:
            self._opened = False
            self.robot.close()
            raise
        return self

    def _require_open(self) -> None:
        if not self._opened:
            raise TeleoperationError("Open the Teleoperator with a context manager first")
        if self.status.state == "fault":
            raise TeleoperationError("Adapter fault is latched; close and reopen before rearming")

    def _call(self, operation: str, *arguments):
        try:
            return getattr(self.robot, operation)(*arguments)
        except Exception as error:
            self.controller.fault(f"adapter_{operation}_failed")
            extra = ""
            if operation in ("send", "read_feedback"):
                try:
                    self.robot.hold("adapter_fault")
                except Exception as hold_error:
                    extra = f"; hold also failed: {hold_error}"
            raise AdapterError(f"Adapter {operation} failed: {error}{extra}") from error

    def _reference(self, reference: RobotFeedback | None) -> RobotFeedback:
        if reference is None and self.robot.capabilities.feedback:
            reference = self._call("read_feedback")
        if not isinstance(reference, RobotFeedback):
            raise TeleoperationError(
                "Provide RobotFeedback explicitly when feedback is unavailable"
            )
        return reference

    def arm(self, reference: RobotFeedback | None = None, *, timeout: float | None = None) -> None:
        self._require_open()
        if self.status.state not in ("disarmed", "tracking_lost"):
            raise TeleoperationError("Disarm before calibrating and arming a new session")
        if self._disconnected:
            raise TeleoperationError("Reconnect tracking before rearming")
        reference = self._reference(reference)
        frame = self.tracker.read(self.config.tracking_timeout if timeout is None else timeout)
        self.last_frame = frame
        health = self.tracker.health
        if health.status != "streaming":
            raise TeleoperationError("Calibration requires tracking that is currently streaming")
        self.controller.arm(frame, reference, frame_age=health.last_frame_age_s or 0.0)

    def disarm(self) -> None:
        self._require_open()
        self.controller.disarm()
        self._call("hold", "disarmed")

    def clutch(self) -> None:
        self._require_open()
        self.controller.clutch()
        self._call("hold", "clutched")

    def release_clutch(self, reference: RobotFeedback | None = None) -> None:
        self._require_open()
        self.controller.release_clutch(self._reference(reference))

    def reconnect(self) -> None:
        self._require_open()
        self.disarm()
        self._disconnected = True
        self.tracker.reconnect()
        self._disconnected = False

    def step(self, *, timeout: float | None = None) -> PoseTarget | None:
        self._require_open()
        if self._disconnected:
            return None
        before = self.status.state
        try:
            frame = self.tracker.read(self.config.tracking_timeout if timeout is None else timeout)
        except StaleFrameError:
            self.controller.tracking_lost("stale_frame")
            frame = None
        except TrackingTimeoutError:
            frame = None
        except ConnectionError:
            self.controller.tracking_lost("disconnected")
            self._disconnected = True
            frame = None
        except Exception:
            self.controller.fault("tracking_failed")
            self._call("hold", "tracking_failed")
            raise
        if frame is not None:
            self.last_frame = frame
        health = self.tracker.health
        if health.status != "streaming":
            reason = "stale_frame" if health.status == "stale" else "tracking_" + health.status
            self.controller.tracking_lost(reason)
            self._disconnected |= health.status in ("disconnected", "error", "closed")
            frame = None
        try:
            target = self.controller.update(frame, frame_age=health.last_frame_age_s or 0.0)
        except Exception:
            self.controller.fault("control_failed")
            self._call("hold", "control_failed")
            raise
        if before in ("active", "clutched") and self.status.state == "tracking_lost":
            self._call("hold", self.status.reason)
        if target is not None:
            self._call("send", target)
        return target

    def close(self) -> None:
        if not self._opened:
            return
        self._opened = False
        self.controller.close()
        try:
            self._call("hold", "closed")
        finally:
            self._call("close")

    def __exit__(self, *_exc) -> None:
        self.close()
