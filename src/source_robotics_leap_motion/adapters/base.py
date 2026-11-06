"""Cartesian adapter contract. Joint-only controllers supply their own kinematics."""

from typing import Protocol

from ..control_models import PoseTarget, RobotCapabilities, RobotFeedback


class RobotAdapter(Protocol):
    capabilities: RobotCapabilities

    def open(self) -> None: ...
    def read_feedback(self) -> RobotFeedback | None: ...
    def send(self, target: PoseTarget) -> None: ...
    def hold(self, reason: str) -> None: ...
    def close(self) -> None: ...


class SessionRobotAdapter(RobotAdapter, Protocol):
    """An adapter with an explicit receiver handshake on arm and clutch resume."""

    def begin_session(self, session_id: str) -> None: ...
