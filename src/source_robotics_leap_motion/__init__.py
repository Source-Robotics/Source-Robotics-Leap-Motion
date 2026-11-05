"""Leap Motion tracking for modern Python. Importing never opens hardware."""

from .errors import (
    ConnectionError,
    LeapError,
    RecordingError,
    RuntimeNotFoundError,
    StaleFrameError,
    TrackingTimeoutError,
)
from .health import TrackingHealth
from .mapping import Mapping
from .models import Bone, Finger, Frame, Hand, Palm, Quaternion, Vector3
from .recording import Recorder, read_recording
from .tracker import Tracker

__version__ = "0.1.0b2"

__all__ = [
    "Bone",
    "ConnectionError",
    "Finger",
    "Frame",
    "Hand",
    "LeapError",
    "Mapping",
    "Palm",
    "Quaternion",
    "Recorder",
    "RecordingError",
    "RuntimeNotFoundError",
    "StaleFrameError",
    "Tracker",
    "TrackingHealth",
    "TrackingTimeoutError",
    "Vector3",
    "read_recording",
]
