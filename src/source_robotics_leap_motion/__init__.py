"""Leap Motion tracking for modern Python. Importing never opens hardware."""

from .control import TeleoperationController, TeleoperationStatus
from .control_config import GripperMapping, TeleoperationConfig, Workspace
from .control_models import Pose, PoseTarget, RobotCapabilities, RobotFeedback
from .errors import (
    AdapterError,
    ConnectionError,
    LeapError,
    RecordingError,
    RuntimeNotFoundError,
    StaleFrameError,
    TeleoperationError,
    TrackingTimeoutError,
)
from .health import TrackingHealth
from .mapping import Mapping
from .models import Bone, Finger, Frame, Hand, Palm, Quaternion, Vector3
from .recording import Recorder, read_recording
from .teleoperation import Teleoperator
from .tracker import Tracker

__version__ = "0.1.0b3"

__all__ = [
    "AdapterError",
    "Bone",
    "ConnectionError",
    "Finger",
    "Frame",
    "Hand",
    "GripperMapping",
    "LeapError",
    "Mapping",
    "Palm",
    "Pose",
    "PoseTarget",
    "Quaternion",
    "Recorder",
    "RecordingError",
    "RuntimeNotFoundError",
    "RobotCapabilities",
    "RobotFeedback",
    "StaleFrameError",
    "Tracker",
    "TrackingHealth",
    "TrackingTimeoutError",
    "TeleoperationConfig",
    "TeleoperationController",
    "TeleoperationError",
    "TeleoperationStatus",
    "Teleoperator",
    "Vector3",
    "Workspace",
    "read_recording",
]
