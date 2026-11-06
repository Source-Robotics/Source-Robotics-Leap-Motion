import threading
import time

import pytest

from source_robotics_leap_motion import (
    AdapterError,
    Pose,
    PoseTarget,
    ReceiverConfig,
    Vector3,
    Workspace,
)
from source_robotics_leap_motion.adapters import SimulatedReceiver


def robot():
    return SimulatedReceiver(
        Pose(Vector3()),
        config=ReceiverConfig(
            Workspace(Vector3(-1, -1, -1), Vector3(1, 1, 1)),
            1,
            interpolation_time=0,
            command_timeout=0.5,
        ),
        update_hz=200,
    )


def test_constructor_is_idle_and_worker_expires_while_the_sender_is_not_calling_it():
    initial_threads = set(threading.enumerate())
    rx = robot()
    assert set(threading.enumerate()) == initial_threads
    rx.open()
    try:
        assert rx.worker_alive
        rx.begin_session("one")
        rx.send(PoseTarget(Vector3(1, 0, 0), None, None, "one", 1, 1, 1, "camera", 0.03))
        # Inspect cached status directly: polling must not perform the watchdog work.
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            with rx._lock:
                expired = rx._receiver.status.state == "expired"
                feedback = rx._receiver.feedback
            if expired:
                break
            threading.Event().wait(0.005)
        assert expired
        assert feedback.pose.position.x == pytest.approx(0.03)
        with pytest.raises(AdapterError, match="not_armed"):
            rx.send(PoseTarget(Vector3(), None, None, "one", 2, 2, 2, "camera", 0.1))
    finally:
        rx.close()
    assert not rx.worker_alive
    assert rx.receiver_status.state == "closed"


def test_failed_worker_is_reported_and_even_failed_close_joins_it(monkeypatch):
    rx = robot()
    rx.open()

    def fail(*, now=None):
        raise OSError("receiver clock failed")

    with rx._lock:
        monkeypatch.setattr(rx._receiver, "advance", fail)
    assert rx._stop.wait(2)
    with pytest.raises(AdapterError, match="worker failed"):
        rx.read_feedback()
    with pytest.raises(OSError, match="clock failed"):
        rx.close()
    assert not rx.worker_alive


def test_reopening_starts_a_new_idle_receiver_and_does_not_replay_targets():
    rx = robot()
    rx.open()
    rx.begin_session("one")
    rx.close()
    rx.open()
    try:
        assert rx.receiver_status.state == "disarmed"
        with pytest.raises(AdapterError, match="not_armed"):
            rx.send(PoseTarget(Vector3(), None, None, "one", 1, 1, 1, "camera", 0.1))
    finally:
        rx.close()
    assert not rx.worker_alive
