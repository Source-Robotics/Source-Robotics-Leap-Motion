"""Immediate Cartesian feedback for demos; no joint geometry or physical dynamics."""

from ..control_models import Pose, PoseTarget, RobotCapabilities, RobotFeedback
from ..errors import AdapterError


class SimulatedArm:
    capabilities = RobotCapabilities(orientation=True, gripper=True, feedback=True)

    def __init__(self, initial_pose: Pose, *, gripper: float = 1.0) -> None:
        self._feedback = RobotFeedback(initial_pose, gripper)
        self.last_target: PoseTarget | None = None
        self.targets_sent = 0
        self.hold_reason = "not_open"
        self._opened = False

    def open(self) -> None:
        if self._opened:
            raise AdapterError("Simulated arm is already open")
        self._opened = True

    def read_feedback(self) -> RobotFeedback:
        self._require_open()
        return self._feedback

    def send(self, target: PoseTarget) -> None:
        self._require_open()
        self._feedback = RobotFeedback(
            Pose(target.position, target.orientation or self._feedback.pose.orientation),
            self._feedback.gripper if target.gripper is None else target.gripper,
        )
        self.last_target = target
        self.targets_sent += 1
        self.hold_reason = ""

    def hold(self, reason: str) -> None:
        self._require_open()
        self.hold_reason = reason

    def close(self) -> None:
        self._opened = False

    def _require_open(self) -> None:
        if not self._opened:
            raise AdapterError("Open the simulated arm first")
