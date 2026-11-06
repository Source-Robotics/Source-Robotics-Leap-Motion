"""Deterministic relative Cartesian control; this module performs no robot I/O."""

from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass
from typing import Literal

from ._geometry import angle, axis_rotation, inverse, multiply, power, slerp
from .control_config import TeleoperationConfig
from .control_models import Pose, PoseTarget, RobotFeedback
from .errors import TeleoperationError
from .models import Frame, Hand

ControlState = Literal["disarmed", "active", "clutched", "tracking_lost", "fault", "closed"]


@dataclass(frozen=True, slots=True)
class TeleoperationStatus:
    state: ControlState
    reason: str
    session_id: str | None
    sequence: int
    hand_id: int | None
    last_target: PoseTarget | None
    workspace_limited: bool = False
    speed_limited: bool = False


class TeleoperationController:
    """Call arm explicitly, then update with fresh frames using one application thread.

    The caller supplies local receipt age. The managed Teleoperator integrates this
    with Tracker's latest mode. No recovery path automatically rearms the controller.
    Local `now` values must come from one monotonic clock; source timestamps are only
    compared with other timestamps in that same source clock domain.
    """

    def __init__(self, config: TeleoperationConfig) -> None:
        self.config = config
        self._state: ControlState = "disarmed"
        self._reason = "not_armed"
        self._session: str | None = None
        self._sequence = 0
        self._hand: Hand | None = None
        self._reference: RobotFeedback | None = None
        self._pose: Pose | None = None
        self._gripper: float | None = None
        self._last_target: PoseTarget | None = None
        self._last_frame: Frame | None = None
        self._last_valid_at: float | None = None
        self._last_output_at: float | None = None
        self._last_now: float | None = None
        self._resume: RobotFeedback | None = None
        self._workspace_limited = self._speed_limited = False
        self._rotation = multiply(config.mapping.rotation, axis_rotation(config.mapping.axes))

    @property
    def status(self) -> TeleoperationStatus:
        return TeleoperationStatus(
            self._state,
            self._reason,
            self._session,
            self._sequence,
            None if self._hand is None else self._hand.id,
            self._last_target,
            self._workspace_limited,
            self._speed_limited,
        )

    def _now(self, now: float | None) -> float:
        value = time.monotonic() if now is None else now
        if not math.isfinite(value) or value < 0:
            self.fault("invalid_control_time")
            raise ValueError("Control time must be finite and non-negative")
        if self._last_now is not None and value < self._last_now:
            self.fault("local_clock_regressed")
            raise TeleoperationError("Control time moved backwards")
        self._last_now = value
        return value

    def _select(self, frame: Frame) -> Hand | None:
        hands = [hand for hand in frame.hands if hand.handedness == self.config.handedness]
        return hands[0] if len(hands) == 1 else None

    def _check_reference(self, reference: RobotFeedback) -> None:
        if not isinstance(reference, RobotFeedback):
            raise TeleoperationError("Supply robot feedback or an explicit RobotFeedback reference")
        if not self.config.workspace.contains(reference.pose.position):
            raise TeleoperationError("Robot reference pose is outside the configured workspace")
        if self.config.gripper is not None and reference.gripper is None:
            raise TeleoperationError("Gripper control requires an explicit gripper reference")

    def _anchor(self, hand: Hand, reference: RobotFeedback, now: float) -> None:
        self._hand = hand
        self._reference = reference
        self._pose = reference.pose
        self._gripper = reference.gripper
        self._last_output_at = now
        self._workspace_limited = self._speed_limited = False

    def arm(
        self,
        frame: Frame,
        reference: RobotFeedback,
        *,
        now: float | None = None,
        frame_age: float = 0.0,
    ) -> None:
        if self._state not in ("disarmed", "tracking_lost"):
            raise TeleoperationError("Disarm before calibrating and arming a new session")
        now = self._now(now)
        self._check_reference(reference)
        if not math.isfinite(frame_age) or not 0 <= frame_age <= self.config.max_frame_age:
            raise TeleoperationError("Calibration requires a fresh frame")
        hand = self._select(frame)
        if hand is None:
            raise TeleoperationError(
                f"Calibration requires exactly one {self.config.handedness} hand"
            )
        self._anchor(hand, reference, now)
        self._last_frame = frame
        self._last_valid_at = now - frame_age
        self._last_target = None
        self._resume = None
        self._sequence = 0
        self._session = uuid.uuid4().hex
        self._state, self._reason = "active", "armed"

    def disarm(self, reason: str = "disarmed") -> None:
        if self._state in ("fault", "closed"):
            return
        self._state, self._reason = "disarmed", reason
        self._resume = None

    def tracking_lost(self, reason: str = "tracking_lost") -> None:
        if self._state in ("active", "clutched"):
            self._state, self._reason = "tracking_lost", reason
            self._resume = None

    def fault(self, reason: str) -> None:
        self._state, self._reason = "fault", reason
        self._resume = None

    def close(self) -> None:
        self._state, self._reason = "closed", "closed"
        self._resume = None

    def clutch(self) -> None:
        if self._state != "active":
            raise TeleoperationError("Clutch requires an active session")
        self._state, self._reason = "clutched", "clutch_engaged"

    def release_clutch(self, reference: RobotFeedback) -> None:
        if self._state != "clutched":
            raise TeleoperationError("Clutch release requires a clutched session")
        self._check_reference(reference)
        self._resume = reference
        self._reason = "waiting_for_reanchor"

    def update(
        self,
        frame: Frame | None,
        *,
        now: float | None = None,
        frame_age: float = 0.0,
    ) -> PoseTarget | None:
        now = self._now(now)
        if self._state not in ("active", "clutched"):
            return None
        if (
            self._last_valid_at is not None
            and now - self._last_valid_at > self.config.tracking_timeout
        ):
            self.tracking_lost("tracking_gap")
            return None
        if not math.isfinite(frame_age) or frame_age < 0:
            self.fault("invalid_frame_age")
            raise ValueError("Frame age must be finite and non-negative")
        if frame is None:
            return None
        if frame_age > self.config.max_frame_age:
            self.tracking_lost("stale_frame")
            return None
        previous = self._last_frame
        if previous is not None:
            if (frame.clock_domain, frame.device_id) != (previous.clock_domain, previous.device_id):
                self.tracking_lost("source_changed")
                return None
            if (frame.id, frame.timestamp_us) == (previous.id, previous.timestamp_us):
                return None
            delta = (frame.timestamp_us - previous.timestamp_us) / 1_000_000
            if delta <= 0 or delta > self.config.tracking_timeout:
                self.tracking_lost("source_clock_reset" if delta <= 0 else "source_gap")
                return None
        hand = self._select(frame)
        if hand is None:
            self.tracking_lost("hand_missing")
            return None
        if self._hand is None or hand.id != self._hand.id:
            self.tracking_lost("hand_changed")
            return None
        self._last_frame = frame
        self._last_valid_at = now - frame_age
        if self._state == "clutched":
            if self._resume is not None:
                self._anchor(hand, self._resume, now)
                self._resume = None
                self._state, self._reason = "active", "clutch_reanchored"
            return None
        if now - self._last_output_at + 1e-12 < 1 / self.config.max_output_hz:
            return None
        try:
            return self._target(frame, hand, now)
        except Exception:
            self.fault("invalid_target")
            raise

    def _target(self, frame: Frame, hand: Hand, now: float) -> PoseTarget:
        config = self.config
        dt = now - self._last_output_at
        alpha = (
            1.0
            if config.smoothing_time_constant == 0
            else -math.expm1(-dt / config.smoothing_time_constant)
        )
        desired = config.mapping.map_position(
            hand.palm.position,
            hand_origin=self._hand.palm.position,
            robot_origin=self._reference.pose.position,
        )
        bounded = config.workspace.clamp(desired)
        self._workspace_limited = desired != bounded
        delta = (bounded - self._pose.position) * alpha
        if (bounded - self._pose.position).norm <= config.position_deadband:
            delta = delta * 0
        limit = config.max_linear_speed * dt
        self._speed_limited = delta.norm > limit
        if delta.norm > limit:
            delta = delta * (limit / delta.norm)
        position = config.workspace.clamp(self._pose.position + delta)
        orientation = self._pose.orientation
        if config.control_orientation:
            camera_delta = multiply(hand.palm.orientation, inverse(self._hand.palm.orientation))
            robot_delta = multiply(multiply(self._rotation, camera_delta), inverse(self._rotation))
            desired_orientation = multiply(
                power(robot_delta, config.rotation_gain), self._reference.pose.orientation
            )
            smoothed = slerp(orientation, desired_orientation, alpha)
            distance = angle(orientation, smoothed)
            fraction = min(1.0, config.max_angular_speed * dt / distance) if distance > 0 else 1.0
            self._speed_limited |= fraction < 1
            orientation = slerp(orientation, smoothed, fraction)
        if config.gripper is not None:
            strength = (
                hand.grab_strength if config.gripper.source == "grab" else hand.pinch_strength
            )
            goal = config.gripper.map(strength)
            delta_grip = (goal - self._gripper) * alpha
            if abs(goal - self._gripper) <= config.gripper.deadband:
                delta_grip = 0.0
            step = config.gripper.max_speed * dt
            self._gripper += max(-step, min(step, delta_grip))
        self._pose = Pose(position, orientation)
        self._sequence += 1
        self._last_output_at = now
        self._last_target = PoseTarget(
            position,
            orientation if config.control_orientation else None,
            self._gripper if config.gripper is not None else None,
            self._session,
            self._sequence,
            frame.id,
            frame.timestamp_us,
            frame.clock_domain,
            min(config.max_frame_age, config.tracking_timeout),
        )
        return self._last_target
