"""Deterministic Cartesian receiver with local expiry and bounded interpolation.

No transport, robot SDK, thread, or source-clock synchronization is involved.
Call advance from a receiver-owned loop independently of the sending application.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Literal

from ._geometry import angle, slerp
from .control_config import Workspace, _number
from .control_models import Pose, PoseTarget, RobotFeedback
from .models import Quaternion, Vector3


@dataclass(frozen=True, slots=True)
class ReceiverConfig:
    workspace: Workspace
    max_linear_speed: float
    max_angular_speed: float = 1.0
    max_gripper_speed: float = 1.0
    interpolation_time: float = 0.04
    command_timeout: float = 0.15

    def __post_init__(self) -> None:
        if not isinstance(self.workspace, Workspace):
            raise ValueError("Receiver workspace must be a Workspace")
        for name in (
            "max_linear_speed",
            "max_angular_speed",
            "max_gripper_speed",
            "command_timeout",
        ):
            _number(getattr(self, name), "Receiver " + name)
        _number(self.interpolation_time, "Receiver interpolation_time", zero=True)
        if self.interpolation_time > self.command_timeout:
            raise ValueError("Receiver interpolation_time must not exceed command_timeout")


@dataclass(frozen=True, slots=True)
class ReceiverStatus:
    state: Literal["disarmed", "armed", "active", "held", "expired", "fault", "closed"]
    reason: str
    session_id: str | None
    sequence: int
    accepted_commands: int
    rejected_commands: int
    last_rejection: str | None
    last_receipt_age_s: float | None


@dataclass(frozen=True, slots=True)
class _Ramp:
    start: Vector3 | Quaternion | float
    goal: Vector3 | Quaternion | float
    started: float
    duration: float
    expires: float

    def sample(self, now: float):
        elapsed = max(0.0, min(now, self.expires) - self.started)
        fraction = 1.0 if self.duration == 0 else min(1.0, elapsed / self.duration)
        if fraction >= 1:
            return self.goal
        if isinstance(self.start, Vector3):
            return self.start + (self.goal - self.start) * fraction
        if isinstance(self.start, Quaternion):
            return slerp(self.start, self.goal, fraction)
        return self.start + (self.goal - self.start) * fraction


class CartesianReceiver:
    """Keep one plan per channel and never replay a FIFO of stale targets.

    Explicit begin_session is required before accepting commands and after expiry.
    Session IDs must be unique per new calibration. A held clutch can resume the
    same session, retaining its sequence watermark; other holds require a new ID.
    Source timestamps are metadata only. Every deadline uses local receipt time.
    """

    def __init__(self, initial: RobotFeedback, *, config: ReceiverConfig) -> None:
        if not isinstance(initial, RobotFeedback):
            raise ValueError("Supply initial RobotFeedback")
        if not config.workspace.contains(initial.pose.position):
            raise ValueError("Initial receiver pose is outside its workspace")
        self.config = config
        self._feedback = initial
        self._state = "disarmed"
        self._reason = "not_armed"
        self._session: str | None = None
        self._sequence = self._accepted = self._rejected = 0
        self._rejection: str | None = None
        self._last_now: float | None = None
        self._received: float | None = None
        self._deadline: float | None = None
        self._resume_allowed = False
        self._position: _Ramp | None = None
        self._orientation: _Ramp | None = None
        self._gripper: _Ramp | None = None

    @property
    def feedback(self) -> RobotFeedback:
        return self._feedback

    @property
    def status(self) -> ReceiverStatus:
        age = None if self._received is None else self._last_now - self._received
        return ReceiverStatus(
            self._state,
            self._reason,
            self._session,
            self._sequence,
            self._accepted,
            self._rejected,
            self._rejection,
            age,
        )

    def _now(self, now: float | None) -> float:
        value = time.monotonic() if now is None else now
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            self.fault("invalid_receiver_time")
            raise ValueError("Receiver time must be finite and non-negative")
        if self._last_now is not None and value < self._last_now:
            self.fault("receiver_clock_regressed")
            raise ValueError("Receiver time moved backwards")
        self._last_now = value
        return value

    def _cancel(self) -> None:
        self._position = self._orientation = self._gripper = None
        self._deadline = None

    def fault(self, reason: str) -> None:
        self._cancel()
        self._resume_allowed = False
        self._state, self._reason = "fault", reason

    def advance(self, *, now: float | None = None) -> RobotFeedback:
        now = self._now(now)
        if self._state not in ("armed", "active"):
            return self._feedback
        effective = min(now, self._deadline)
        pose = self._feedback.pose
        position = pose.position if self._position is None else self._position.sample(effective)
        orientation = (
            pose.orientation if self._orientation is None else self._orientation.sample(effective)
        )
        gripper = (
            self._feedback.gripper if self._gripper is None else self._gripper.sample(effective)
        )
        self._feedback = RobotFeedback(Pose(position, orientation), gripper)
        if now >= self._deadline:
            self._cancel()
            self._resume_allowed = False
            self._state, self._reason = "expired", "command_expired"
        return self._feedback

    def begin_session(
        self, session_id: str, *, after_sequence: int | None = None, now: float | None = None
    ) -> None:
        self.advance(now=now)
        if not isinstance(session_id, str) or not session_id or len(session_id) > 128:
            raise ValueError("Session ID must be a non-empty string of at most 128 characters")
        if self._state in ("fault", "closed"):
            raise ValueError("Reopen the receiver after fault or close")
        same = session_id == self._session
        if same and not self._resume_allowed:
            raise ValueError("Use a new session after disarming or command expiry")
        if after_sequence is None:
            if same:
                raise ValueError("Resume requires the sender's sequence watermark")
            after_sequence = 0
        if type(after_sequence) is not int or after_sequence < 0:
            raise ValueError("Session sequence watermark must be a non-negative integer")
        if self._state in ("armed", "active"):
            raise ValueError("Hold the current receiver session before starting another")
        if same and after_sequence < self._sequence:
            raise ValueError("Session sequence watermark must not move backwards")
        self._cancel()
        self._sequence = after_sequence
        self._session = session_id
        self._received = None
        self._resume_allowed = False
        self._deadline = self._last_now + self.config.command_timeout
        self._state, self._reason = "armed", "waiting_for_command"

    def _reject(self, reason: str) -> bool:
        self._rejected += 1
        self._rejection = reason
        return False

    def accept(self, target: PoseTarget, *, now: float | None = None) -> bool:
        self.advance(now=now)
        if self._state not in ("armed", "active"):
            return self._reject("receiver_not_armed")
        if not isinstance(target, PoseTarget):
            return self._reject("invalid_target")
        if target.session_id != self._session:
            return self._reject("session_mismatch")
        if type(target.sequence) is not int or target.sequence <= self._sequence:
            return self._reject("sequence_not_increasing")
        if (
            not isinstance(target.position, Vector3)
            or (target.orientation is not None and not isinstance(target.orientation, Quaternion))
            or (
                target.gripper is not None
                and (
                    isinstance(target.gripper, bool)
                    or not isinstance(target.gripper, (int, float))
                    or not math.isfinite(target.gripper)
                    or not 0 <= target.gripper <= 1
                )
            )
            or isinstance(target.valid_for_s, bool)
            or not isinstance(target.valid_for_s, (int, float))
            or not math.isfinite(target.valid_for_s)
            or target.valid_for_s <= 0
            or type(target.source_frame_id) is not int
            or target.source_frame_id < 0
            or type(target.source_timestamp_us) is not int
            or target.source_timestamp_us < 0
            or not isinstance(target.clock_domain, str)
            or not target.clock_domain
        ):
            return self._reject("invalid_target")
        if not self.config.workspace.contains(target.position):
            return self._reject("outside_workspace")
        if target.gripper is not None and self._feedback.gripper is None:
            return self._reject("missing_gripper_reference")
        now = self._last_now
        deadline = now + min(target.valid_for_s, self.config.command_timeout)
        current = self._feedback
        duration = max(
            self.config.interpolation_time,
            (target.position - current.pose.position).norm / self.config.max_linear_speed,
        )
        self._position = _Ramp(current.pose.position, target.position, now, duration, deadline)
        if target.orientation is not None:
            duration = max(
                self.config.interpolation_time,
                angle(current.pose.orientation, target.orientation) / self.config.max_angular_speed,
            )
            self._orientation = _Ramp(
                current.pose.orientation, target.orientation, now, duration, deadline
            )
        if target.gripper is not None:
            duration = max(
                self.config.interpolation_time,
                abs(target.gripper - current.gripper) / self.config.max_gripper_speed,
            )
            self._gripper = _Ramp(current.gripper, target.gripper, now, duration, deadline)
        self._received, self._deadline = now, deadline
        self._sequence = target.sequence
        self._accepted += 1
        self._rejection = None
        self._state, self._reason = "active", "interpolating"
        return True

    def hold(self, reason: str = "held", *, now: float | None = None) -> None:
        self.advance(now=now)
        if self._state in ("fault", "closed"):
            return
        self._resume_allowed = reason == "clutched" and (
            self._state in ("armed", "active") or self._resume_allowed
        )
        self._cancel()
        self._state, self._reason = "held", reason

    def close(self, *, now: float | None = None) -> None:
        try:
            self.advance(now=now)
        finally:
            self._cancel()
            self._resume_allowed = False
            self._state, self._reason = "closed", "closed"
