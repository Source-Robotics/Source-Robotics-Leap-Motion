"""Bounded, thread-safe tracking statistics; ages use the local monotonic clock."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Literal

from .errors import ConnectionError
from .models import Frame

TrackingMode = Literal["sequential", "latest"]
TrackingStatus = Literal[
    "closed", "starting", "waiting", "streaming", "stale", "disconnected", "ended", "error"
]


@dataclass(frozen=True, slots=True)
class TrackingHealth:
    """An immutable snapshot of one tracking session.

    ``last_frame_age_s`` is time since Python received the last distinct frame,
    not camera-to-application latency. ``received_fps`` measures distinct local
    arrivals over at most 120 frames. No hands still counts as streaming.
    ``skipped_frames`` counts frames deliberately omitted by latest mode, not
    frames lost upstream. Counters restart on open/reconnect.
    """

    mode: TrackingMode
    status: TrackingStatus
    received_frames: int = 0
    delivered_frames: int = 0
    skipped_frames: int = 0
    duplicate_frames: int = 0
    read_timeouts: int = 0
    timestamp_resets: int = 0
    received_fps: float = 0.0
    last_frame_age_s: float | None = None
    last_frame_id: int | None = None
    last_frame_timestamp_us: int | None = None
    device_id: int | None = None
    clock_domain: str | None = None
    last_hand_count: int | None = None
    last_error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class _HealthMonitor:
    def __init__(self, mode: TrackingMode, max_age: float) -> None:
        self._lock = threading.Lock()
        self.mode = mode
        self.max_age = max_age
        self.state: TrackingStatus = "closed"
        self.received = self.delivered = self.skipped = self.duplicates = 0
        self.timeouts = self.resets = 0
        self.last_error: str | None = None
        self._key: tuple | None = None
        self._last: float | None = None
        self._arrivals: deque[float] = deque(maxlen=120)
        self._hand_count: int | None = None

    def set_state(self, state: TrackingStatus) -> None:
        with self._lock:
            self.state = state

    def receive(self, frame: Frame, now: float) -> bool:
        key = (frame.clock_domain, frame.device_id, frame.id, frame.timestamp_us)
        with self._lock:
            self.received += 1
            if key == self._key:
                self.duplicates += 1
                return False
            if self._key is not None and key[:2] == self._key[:2] and key[3] < self._key[3]:
                self.resets += 1
            self._key = key
            self._last = now
            self._hand_count = len(frame.hands)
            self._arrivals.append(now)
            self.state = "streaming"
            return True

    def deliver(self) -> None:
        with self._lock:
            self.delivered += 1

    def skip(self) -> None:
        with self._lock:
            self.skipped += 1

    def timeout(self) -> None:
        with self._lock:
            self.timeouts += 1

    def fail(self, error: BaseException) -> None:
        with self._lock:
            self.last_error = f"{type(error).__name__}: {error}"
            self.state = (
                "disconnected" if isinstance(error, (ConnectionError, OSError)) else "error"
            )

    def snapshot(self) -> TrackingHealth:
        with self._lock:
            now = time.perf_counter()
            age = None if self._last is None else max(0.0, now - self._last)
            status = self.state
            if status == "streaming" and age is not None and age > self.max_age:
                status = "stale"
            fps = 0.0
            if status == "streaming" and len(self._arrivals) > 1:
                span = self._arrivals[-1] - self._arrivals[0]
                if span > 0:
                    fps = (len(self._arrivals) - 1) / span
            return TrackingHealth(
                mode=self.mode,
                status=status,
                received_frames=self.received,
                delivered_frames=self.delivered,
                skipped_frames=self.skipped,
                duplicate_frames=self.duplicates,
                read_timeouts=self.timeouts,
                timestamp_resets=self.resets,
                received_fps=fps,
                last_frame_age_s=age,
                last_frame_id=None if self._key is None else self._key[2],
                last_frame_timestamp_us=None if self._key is None else self._key[3],
                device_id=None if self._key is None else self._key[1],
                clock_domain=None if self._key is None else self._key[0],
                last_hand_count=self._hand_count,
                last_error=self.last_error,
            )
