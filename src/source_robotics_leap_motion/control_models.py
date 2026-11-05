"""Owned Cartesian commands and explicit robot integration capabilities."""

from dataclasses import dataclass

from .models import Quaternion, Vector3


@dataclass(frozen=True, slots=True)
class Pose:
    position: Vector3
    orientation: Quaternion = Quaternion()

    def __post_init__(self) -> None:
        if not isinstance(self.position, Vector3) or not isinstance(self.orientation, Quaternion):
            raise ValueError("A Pose requires a Vector3 position and Quaternion orientation")


@dataclass(frozen=True, slots=True)
class RobotFeedback:
    pose: Pose
    gripper: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.pose, Pose):
            raise ValueError("Robot feedback must contain a Pose")
        if self.gripper is not None and not 0 <= self.gripper <= 1:
            raise ValueError("Gripper feedback must be normalized to [0, 1]")


@dataclass(frozen=True, slots=True)
class PoseTarget:
    """A Cartesian command; None leaves orientation/gripper under robot control.

    Positions are metres, orientation is x/y/z/w in the configured robot frame,
    and gripper values are normalized. Receivers expire commands using their own
    monotonic receipt time and ``valid_for_s``, never the source clock.
    """

    position: Vector3
    orientation: Quaternion | None
    gripper: float | None
    session_id: str
    sequence: int
    source_frame_id: int
    source_timestamp_us: int
    clock_domain: str
    valid_for_s: float


@dataclass(frozen=True, slots=True)
class RobotCapabilities:
    cartesian_position: bool = True
    orientation: bool = False
    gripper: bool = False
    feedback: bool = False
