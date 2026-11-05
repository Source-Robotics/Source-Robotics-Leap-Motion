"""A replay source with optional acquisition-time pacing."""

import math
import time
from pathlib import Path

from ..errors import RecordingError
from ..recording import read_recording


class ReplayBackend:
    name = "replay"

    def __init__(self, path: str | Path, *, realtime: bool = False, speed: float = 1.0):
        if not math.isfinite(speed) or speed <= 0:
            raise ValueError("Replay speed must be positive and finite")
        self.path = Path(path)
        self.realtime = realtime
        self.speed = speed
        self._frames = None
        self._pending = None
        self._origin = None
        self._clock_domain = None
        self._last_timestamp = None
        self._start = 0.0

    def open(self) -> None:
        self._frames = read_recording(self.path)
        self._pending = None
        self._origin = None
        self._clock_domain = None
        self._last_timestamp = None
        self._start = time.perf_counter()

    def read(self, timeout: float):
        if self._frames is None:
            raise RuntimeError("Replay is not open")
        if self._pending is None:
            self._pending = next(self._frames)
        frame = self._pending
        if self._origin is None:
            self._origin = frame.timestamp_us
            self._clock_domain = frame.clock_domain
        if self.realtime:
            if frame.clock_domain != self._clock_domain or (
                self._last_timestamp is not None and frame.timestamp_us < self._last_timestamp
            ):
                raise RecordingError("Paced replay requires one monotonically increasing clock")
            due = self._start + (frame.timestamp_us - self._origin) / 1_000_000 / self.speed
            delay = due - time.perf_counter()
            if delay > 0:
                time.sleep(min(delay, timeout))
                if delay > timeout:
                    return None
        self._last_timestamp = frame.timestamp_us
        self._pending = None
        return frame

    def close(self) -> None:
        if self._frames is not None:
            self._frames.close()
            self._frames = None
        self._pending = None
