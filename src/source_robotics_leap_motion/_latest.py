"""Single-slot acquisition. All source methods run on the same owning thread."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from .errors import ConnectionError, StaleFrameError, TrackingTimeoutError
from .health import _HealthMonitor
from .models import Frame

if TYPE_CHECKING:
    from .tracker import FrameSource


class _LatestReader:
    _poll_interval = 0.05
    _shutdown_timeout = 5.0

    def __init__(self, source: FrameSource, health: _HealthMonitor, max_age: float) -> None:
        self._source = source
        self._health = health
        self._max_age = max_age
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._opened = False
        self._ended = False
        self._error: BaseException | None = None
        self._close_error: BaseException | None = None
        self._pending: tuple[Frame, float] | None = None
        self._thread = threading.Thread(target=self._run, name="source-leap-reader", daemon=True)

    @property
    def alive(self) -> bool:
        return self._thread.is_alive()

    def start(self) -> None:
        self._thread.start()
        # Opening can include a first-run runtime download, so it has no artificial
        # frame deadline. Short waits allow KeyboardInterrupt during startup.
        while not self._ready.wait(self._poll_interval):
            pass
        if not self._opened and self._error is not None:
            raise self._error.with_traceback(None)

    def _discard(self) -> None:
        if self._pending is not None:
            self._pending = None
            self._health.skip()

    def _run(self) -> None:
        try:
            self._source.open()
            self._opened = True
            self._health.set_state("waiting")
            self._ready.set()
            while not self._stop.is_set():
                before = time.perf_counter()
                frame = self._source.read(self._poll_interval)
                received = time.perf_counter()
                if frame is None:
                    # A custom source may return None immediately. Avoid a busy loop.
                    self._stop.wait(max(0.0, self._poll_interval - (received - before)))
                    continue
                with self._condition:
                    if self._stop.is_set():
                        break
                    if not self._health.receive(frame, received):
                        self._health.skip()
                    else:
                        self._discard()
                        self._pending = (frame, received)
                        self._condition.notify_all()
        except StopIteration:
            with self._condition:
                self._ended = True
                self._health.set_state("ended")
                self._condition.notify_all()
        except BaseException as error:
            self._fail(error)
        finally:
            try:
                self._source.close()
            except BaseException as error:
                self._close_error = error
                self._fail(error)
            self._ready.set()
            with self._condition:
                self._condition.notify_all()

    def _fail(self, error: BaseException) -> None:
        with self._condition:
            self._discard()
            if self._error is None:
                self._error = error
                self._health.fail(error)
            self._condition.notify_all()

    def read(self, timeout: float) -> Frame:
        deadline = time.perf_counter() + timeout
        with self._condition:
            while True:
                if self._stop.is_set():
                    raise RuntimeError("Tracker is closed")
                if self._error is not None:
                    raise self._error.with_traceback(None)
                now = time.perf_counter()
                if self._pending is not None:
                    frame, received = self._pending
                    if now - received <= self._max_age:
                        self._pending = None
                        self._health.deliver()
                        return frame
                    self._discard()
                if self._ended:
                    raise StopIteration
                remaining = deadline - now
                if remaining <= 0:
                    self._health.timeout()
                    health = self._health.snapshot()
                    if health.last_frame_age_s is not None and (
                        health.last_frame_age_s > self._max_age
                    ):
                        raise StaleFrameError(
                            f"No fresh tracking frame within {timeout:g}s; last distinct frame "
                            f"arrived {health.last_frame_age_s:.3f}s ago "
                            f"(limit {self._max_age:g}s)."
                        )
                    raise TrackingTimeoutError(f"No new tracking frame within {timeout:g}s.")
                self._condition.wait(remaining)

    def close(self) -> None:
        self._stop.set()
        with self._condition:
            self._discard()
            self._condition.notify_all()
        if self._thread.ident is not None:
            self._thread.join(self._shutdown_timeout)
        if self.alive:
            error = ConnectionError(
                "Tracking source did not stop within the shutdown deadline. Custom sources "
                "must honor read(timeout); reconnect is unavailable until it stops."
            )
            self._health.fail(error)
            raise error
        if self._close_error is not None:
            raise self._close_error.with_traceback(None)
