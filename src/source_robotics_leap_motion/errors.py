"""Public exceptions, independent of the native runtime."""


class LeapError(Exception):
    """Base error for tracking, recording, and teleoperation."""


class RuntimeNotFoundError(LeapError):
    """A compatible LeapC client library could not be found or loaded."""


class ConnectionError(LeapError):
    """The tracking service is unavailable or disconnected."""


class TrackingTimeoutError(LeapError):
    """No tracking frame arrived within the requested deadline."""


class RecordingError(LeapError):
    """A recording is invalid, unsupported, or truncated."""
