import queue
import threading
import time
from dataclasses import FrozenInstanceError

import pytest

from source_robotics_leap_motion import (
    ConnectionError,
    Frame,
    StaleFrameError,
    Tracker,
    TrackingTimeoutError,
)
from source_robotics_leap_motion._latest import _LatestReader
from source_robotics_leap_motion.health import _HealthMonitor


class Source:
    def __init__(self):
        self.queue = queue.Queue()
        self.calls = []
        self.closed = threading.Event()

    def open(self):
        self.calls.append(("open", threading.get_ident()))
        self.closed.clear()

    def read(self, timeout):
        self.calls.append(("read", threading.get_ident()))
        try:
            item = self.queue.get(timeout=timeout)
        except queue.Empty:
            return None
        if isinstance(item, BaseException):
            raise item
        return item

    def close(self):
        self.calls.append(("close", threading.get_ident()))
        self.closed.set()


def wait_until(predicate, timeout=3):
    deadline = time.perf_counter() + timeout
    while not predicate():
        if time.perf_counter() >= deadline:
            pytest.fail("Reader did not reach the expected state")
        time.sleep(0.001)


def test_latest_has_one_slot_and_never_repeats_a_consumed_frame():
    source = Source()
    with Tracker(backend=source, mode="latest", max_frame_age=5) as tracker:
        for index in range(100):
            source.queue.put(Frame(index, index))
        wait_until(lambda: tracker.health.received_frames == 100)
        assert tracker.read().id == 99
        health = tracker.health
        assert health.status == "streaming"
        assert health.last_hand_count == 0  # No hands is not a connection fault.
        assert (health.received_frames, health.delivered_frames, health.skipped_frames) == (
            100,
            1,
            99,
        )
        with pytest.raises(TrackingTimeoutError):
            tracker.read(timeout=0.01)
        assert tracker.health.read_timeouts == 1
        with pytest.raises(FrozenInstanceError):
            health.status = "closed"
    assert tracker.health.status == "closed"
    assert source.closed.is_set()
    owners = {owner for _name, owner in source.calls}
    assert len(owners) == 1 and threading.get_ident() not in owners
    assert [name for name, _owner in source.calls].count("close") == 1
    tracker.close()  # Idempotent, without closing the source twice.
    assert [name for name, _owner in source.calls].count("close") == 1


def test_stale_pending_frame_is_discarded_and_duplicate_does_not_refresh_it():
    source = Source()
    with Tracker(backend=source, mode="latest", max_frame_age=0.02) as tracker:
        frame = Frame(1, 1)
        source.queue.put(frame)
        wait_until(lambda: tracker.health.received_frames == 1)
        wait_until(lambda: tracker.health.last_frame_age_s > 0.04)
        source.queue.put(frame)
        wait_until(lambda: tracker.health.duplicate_frames == 1)
        assert tracker.health.status == "stale"
        with pytest.raises(StaleFrameError):
            tracker.read(timeout=0.01)
        assert tracker.health.skipped_frames == 2
        source.queue.put(Frame(2, 2))
        assert tracker.read().id == 2
        assert tracker.health.status == "streaming"


@pytest.mark.parametrize("error", [ConnectionError("USB lost"), ValueError("Invalid frame")])
def test_source_failure_invalidates_pending_data_and_preserves_error_type(error):
    source = Source()
    with Tracker(backend=source, mode="latest", max_frame_age=5) as tracker:
        source.queue.put(Frame(1, 1))
        source.queue.put(error)
        wait_until(lambda: source.closed.is_set())
        for _ in range(3):
            with pytest.raises(type(error), match=str(error)):
                tracker.read()
        health = tracker.health
        assert health.delivered_frames == 0 and health.skipped_frames == 1
        assert health.status == ("disconnected" if isinstance(error, ConnectionError) else "error")
        assert str(error) in health.last_error


def test_latest_eof_delivers_final_unread_frame_once():
    source = Source()
    source.queue.put(Frame(1, 1))
    source.queue.put(Frame(2, 2))
    source.queue.put(StopIteration())
    with Tracker(backend=source, mode="latest", max_frame_age=5) as tracker:
        wait_until(lambda: source.closed.is_set())
        assert tracker.read().id == 2
        with pytest.raises(StopIteration):
            tracker.read()
        assert tracker.health.status == "ended"


def test_latest_open_failure_closes_on_owner_thread_without_leaking_worker():
    class Failed(Source):
        def open(self):
            super().open()
            raise OSError("Cannot open")

    source = Failed()
    tracker = Tracker(backend=source, mode="latest")
    with pytest.raises(OSError, match="Cannot open"):
        with tracker:
            pass
    assert source.closed.is_set()
    assert len({owner for _name, owner in source.calls}) == 1
    assert not tracker._reader.alive
    tracker.close()


def test_close_wakes_waiting_consumer_and_reconnect_starts_a_new_session():
    source = Source()
    tracker = Tracker(backend=source, mode="latest")
    errors = queue.Queue()
    waiting = threading.Event()

    def consume():
        waiting.set()
        try:
            tracker.read(timeout=30)
        except BaseException as error:
            errors.put(error)

    with tracker:
        consumer = threading.Thread(target=consume)
        consumer.start()
        assert waiting.wait(3)
        tracker.close()
        consumer.join(3)
        assert not consumer.is_alive()
        assert isinstance(errors.get_nowait(), RuntimeError)
        tracker.reconnect()
        assert tracker.health.received_frames == 0
        source.queue.put(Frame(10, 20))
        assert tracker.read().id == 10
    assert not any(thread.name == "source-leap-reader" for thread in threading.enumerate())


def test_misbehaving_source_shutdown_is_bounded_and_prevents_unsafe_reopen(monkeypatch):
    release = threading.Event()
    reading = threading.Event()

    class Blocking(Source):
        def read(self, timeout):
            reading.set()
            release.wait(5)
            return Frame(1, 1)

    monkeypatch.setattr(_LatestReader, "_shutdown_timeout", 0.02)
    source = Blocking()
    tracker = Tracker(backend=source, mode="latest")
    tracker.__enter__()
    assert reading.wait(3)
    try:
        with pytest.raises(ConnectionError, match="shutdown deadline"):
            tracker.close()
        assert not source.closed.is_set()  # Never close a source concurrently with its read.
        with pytest.raises(RuntimeError, match="still stopping"):
            tracker.__enter__()
    finally:
        release.set()
        assert source.closed.wait(3)
        tracker.close()
    assert tracker.health.received_frames == 0


def test_read_during_final_close_never_polls_source_from_a_different_thread(monkeypatch):
    source = Source()
    tracker = Tracker(backend=source, mode="latest")
    tracker.__enter__()
    finishing = threading.Event()
    finish = threading.Event()
    original_set_state = tracker._health.set_state

    def set_state(state):
        if state == "closed":
            finishing.set()
            assert finish.wait(3)
        original_set_state(state)

    monkeypatch.setattr(tracker._health, "set_state", set_state)
    closer = threading.Thread(target=tracker.close)
    closer.start()
    try:
        assert finishing.wait(3)
        with pytest.raises(RuntimeError, match="closed"):
            tracker.read(timeout=0.01)
    finally:
        finish.set()
        closer.join(3)
    assert not closer.is_alive()
    assert len({owner for _name, owner in source.calls}) == 1


def test_health_uses_local_arrivals_reports_clock_reset_and_bounds_history(monkeypatch):
    health = _HealthMonitor("latest", 0.1)
    health.set_state("waiting")
    assert health.snapshot().last_frame_age_s is None
    for index in range(150):
        health.receive(Frame(index, 1_000_000 + index), index * 0.01)
    monkeypatch.setattr("source_robotics_leap_motion.health.time.perf_counter", lambda: 1.5)
    snapshot = health.snapshot()
    assert snapshot.received_fps == pytest.approx(100)
    assert snapshot.last_frame_age_s == pytest.approx(0.01)
    assert snapshot.last_hand_count == 0
    assert len(health._arrivals) == 120
    health.receive(Frame(151, 10), 1.5)
    assert health.snapshot().timestamp_resets == 1
    monkeypatch.setattr("source_robotics_leap_motion.health.time.perf_counter", lambda: 2)
    assert health.snapshot().status == "stale"
    assert health.snapshot().received_fps == 0


def test_sequential_health_preserves_every_frame_and_resets_on_reopen():
    source = Source()
    tracker = Tracker(backend=source)
    with tracker:
        frame = Frame(1, 1)
        for _ in range(2):
            source.queue.put(frame)
            assert tracker.read() is frame
        assert tracker.health.received_frames == tracker.health.delivered_frames == 2
        assert tracker.health.duplicate_frames == 1
        assert tracker.health.skipped_frames == 0
    with tracker:
        assert tracker.health.received_frames == 0
        with pytest.raises(TrackingTimeoutError):
            tracker.read(timeout=0.001)
        assert tracker.health.status == "waiting"


@pytest.mark.parametrize("mode", ["invalid", "", None])
def test_rejects_unknown_modes(mode):
    with pytest.raises(ValueError, match="Mode"):
        Tracker(mode=mode)


@pytest.mark.parametrize("age", [0, -1, float("inf"), float("nan")])
def test_rejects_invalid_age_limits(age):
    with pytest.raises(ValueError, match="age"):
        Tracker(max_frame_age=age)


def test_latest_demo_is_paced_and_runs_without_hardware():
    with pytest.raises(ValueError, match="pacing"):
        Tracker.demo(mode="latest", realtime=False)
    with Tracker.demo(mode="latest") as tracker:
        first = tracker.read()
        assert tracker.read().timestamp_us > first.timestamp_us
