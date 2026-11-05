"""Deterministic synthetic frames for trying the API without a camera."""

import math
import time

from ..models import Frame, Hand, Palm, Vector3


class DemoBackend:
    name = "demo"

    def __init__(self, rate: float = 60.0, *, realtime: bool = True) -> None:
        if not math.isfinite(rate) or not 1 <= rate <= 1000:
            raise ValueError("Demo frame rate must be between 1 and 1000 Hz")
        self.rate = rate
        self.realtime = realtime
        self._index = 0
        self._next = 0.0

    def open(self) -> None:
        self._index = 0
        self._next = time.perf_counter()

    def read(self, timeout: float) -> Frame | None:
        delay = self._next - time.perf_counter()
        if self.realtime and delay > 0:
            time.sleep(min(delay, timeout))
            if delay > timeout:
                return None
        elapsed = self._index / self.rate
        position = Vector3(0.06 * math.sin(elapsed), 0.25, -0.06 * math.cos(elapsed))
        hand = Hand(
            id=1,
            handedness="right",
            palm=Palm(position=position),
            grab_strength=(1 + math.sin(elapsed)) / 2,
            visible_time_us=round(elapsed * 1_000_000),
        )
        frame = Frame(
            id=self._index,
            timestamp_us=round(elapsed * 1_000_000),
            hands=(hand,),
            framerate=self.rate,
            clock_domain="demo",
        )
        self._index += 1
        self._next = time.perf_counter() + 1 / self.rate
        return frame

    def close(self) -> None:
        pass
