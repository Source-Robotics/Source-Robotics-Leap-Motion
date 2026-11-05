"""Public exceptions, independent of the native runtime."""


class LeapError(Exception):
    """Base error for tracking, recording, and teleoperation."""


class RuntimeNotFoundError(LeapError):
    """A compatible LeapC client library could not be found or loaded."""


class ConnectionError(LeapError):
    """The tracking service is unavailable or disconnected."""


class TrackingTimeoutError(LeapError):
    """No tracking frame arrived within the requested deadline."""


class StaleFrameError(TrackingTimeoutError):
    """Latest mode has received frames, but no unread frame is fresh enough."""


class RecordingError(LeapError):
    """A recording is invalid, unsupported, or truncated."""


class TeleoperationError(LeapError):
    """Invalid control state, calibration, or robot integration."""


class AdapterError(TeleoperationError):
    """Robot adapter operation failed; inspect the chained original exception."""
