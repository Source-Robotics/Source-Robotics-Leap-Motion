"""Context-managed tracking with interchangeable live, demo, and replay sources."""

from __future__ import annotations

import math
import os
from collections.abc import Iterator
from typing import Protocol

from ._compat import Self
from .errors import TrackingTimeoutError
from .models import Frame


class FrameSource(Protocol):
    def open(self) -> None: ...
    def read(self, timeout: float) -> Frame | None: ...
    def close(self) -> None: ...


class Tracker:
    """Use inside a with block. A timeout is distinct from an empty-hand frame.

    Native frames use Leap's camera axes (+x right, +y up, +z toward the user).
    Positions and velocities are converted to metres and metres/second.
    """

    def __init__(
        self,
        *,
        backend: FrameSource | None = None,
        library_path: str | None = None,
        runtime_dir: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Timeout must be positive and finite")
        if sum(option is not None for option in (backend, library_path, runtime_dir)) > 1:
            raise ValueError("Choose a backend, a native library, or a local runtime directory")
        self._backend = backend
        self._library_path = library_path
        self._runtime_dir = runtime_dir
        self.timeout = timeout
        self._opened = False

    @classmethod
    def demo(cls, *, rate: float = 60.0, realtime: bool = True) -> Self:
        from .backends.demo import DemoBackend

        return cls(backend=DemoBackend(rate, realtime=realtime))

    def __enter__(self) -> Self:
        if self._opened:
            raise RuntimeError("Tracker is already open")
        if self._backend is None:
            if self._runtime_dir is not None:
                from .backends.shared import SharedRuntimeBackend

                self._backend = SharedRuntimeBackend(
                    self._runtime_dir, connect_timeout=self.timeout
                )
            elif self._library_path is not None or os.environ.get("SOURCE_LEAP_LIBRARY"):
                from .backends.leapc import LeapCBackend

                self._backend = LeapCBackend(self._library_path, connect_timeout=self.timeout)
            else:
                from .backends.auto import AutoBackend

                self._backend = AutoBackend(connect_timeout=self.timeout)
        try:
            self._backend.open()
        except BaseException:
            self._backend.close()
            raise
        self._opened = True
        return self

    @property
    def backend_name(self) -> str:
        return getattr(self._backend, "name", "custom")

    @property
    def runtime_details(self) -> dict | None:
        return getattr(self._backend, "details", None)

    def read(self, timeout: float | None = None) -> Frame:
        if not self._opened or self._backend is None:
            raise RuntimeError("Open the tracker with 'with Tracker() as tracker:' first")
        deadline = self.timeout if timeout is None else timeout
        if not math.isfinite(deadline) or deadline <= 0:
            raise ValueError("Timeout must be positive and finite")
        frame = self._backend.read(deadline)
        if frame is None:
            raise TrackingTimeoutError(
                f"No tracking frames within {deadline:g}s. Check camera USB connection "
                "and tracking service. An empty-hand frame would still be returned."
            )
        return frame

    def __iter__(self) -> Iterator[Frame]:
        while self._opened:
            try:
                yield self.read()
            except StopIteration:
                return

    def close(self) -> None:
        try:
            if self._backend is not None:
                self._backend.close()
        finally:
            self._opened = False

    def reconnect(self) -> Self:
        """Explicitly discard a failed connection and open a fresh tracking session."""
        self.close()
        return self.__enter__()

    def __exit__(self, *_exc) -> None:
        self.close()
