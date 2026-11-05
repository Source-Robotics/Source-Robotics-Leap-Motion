from collections import deque
from types import SimpleNamespace

import pytest

from source_robotics_leap_motion import (
    AdapterError,
    ConnectionError,
    Frame,
    Hand,
    Palm,
    Pose,
    RobotCapabilities,
    RobotFeedback,
    StaleFrameError,
    TeleoperationConfig,
    TeleoperationError,
    Teleoperator,
    TrackingTimeoutError,
    Vector3,
    Workspace,
)
from source_robotics_leap_motion.adapters import CallbackAdapter, SimulatedArm


class Source:
    max_frame_age = 0.05

    def __init__(self):
        self.health = SimpleNamespace(status="streaming", mode="latest", last_frame_age_s=0)
        self.now = 0
        self.events = deque()
        self.index = 0
        self.reconnects = 0

    def read(self, timeout):
        self.now += 0.05
        if self.events:
            event = self.events.popleft()
            if isinstance(event, BaseException):
                raise event
            return event
        self.index += 1
        return Frame(
            self.index,
            self.index * 50_000,
            (Hand(1, "right", Palm(Vector3(self.index / 100, 0, 0))),),
        )

    def reconnect(self):
        self.reconnects += 1
        self.health.status = "streaming"


@pytest.fixture
def setup(monkeypatch):
    source = Source()
    monkeypatch.setattr("source_robotics_leap_motion.control.time.monotonic", lambda: source.now)
    config = TeleoperationConfig(
        Workspace(Vector3(-1, -1, -1), Vector3(1, 1, 1)),
        max_linear_speed=1,
        smoothing_time_constant=0,
        position_deadband=0,
    )
    robot = SimulatedArm(Pose(Vector3()))
    return source, config, robot


def test_managed_session_starts_disarmed_owns_adapter_and_keeps_tracker_open(setup):
    source, config, robot = setup
    manager = Teleoperator(source, robot=robot, config=config)
    with manager:
        assert robot.hold_reason == "disarmed"
        assert manager.step() is None and robot.targets_sent == 0
        manager.arm()
        assert robot.targets_sent == 0
        assert manager.step() is robot.last_target
        manager.clutch()
        assert robot.hold_reason == "clutched"
        before = robot.targets_sent
        assert manager.step() is None
        assert robot.targets_sent == before
        manager.release_clutch()
        assert manager.step() is None
        assert manager.step() is not None
    assert manager.status.state == "closed"
    assert source.health.status == "streaming"
    with pytest.raises(AdapterError):
        robot.read_feedback()
    manager.close()


@pytest.mark.parametrize(
    "event", [StaleFrameError("stale"), ConnectionError("unplugged"), Frame(200, 150_000)]
)
def test_tracking_loss_sends_hold_once_and_requires_explicit_rearm(setup, event):
    source, config, robot = setup
    holds = []
    callback = CallbackAdapter(
        lambda target: None, hold=holds.append, feedback=lambda: RobotFeedback(Pose(Vector3()))
    )
    with Teleoperator(source, robot=callback, config=config) as manager:
        manager.arm()
        source.events.append(event)
        assert manager.step() is None
        assert manager.status.state == "tracking_lost"
        assert len(holds) == 2  # Startup hold and one loss transition.
        manager.step()
        assert len(holds) == 2
        if isinstance(event, ConnectionError):
            with pytest.raises(TeleoperationError, match="Reconnect"):
                manager.arm()
            manager.reconnect()
            assert source.reconnects == 1
        manager.arm()
        assert manager.status.state == "active"


def test_short_poll_timeout_does_not_disarm_but_expired_tracking_does(setup):
    source, config, robot = setup
    with Teleoperator(source, robot=robot, config=config) as manager:
        manager.arm()
        source.events.append(TrackingTimeoutError("poll"))
        assert manager.step(timeout=0.01) is None
        assert manager.status.state == "active"
        source.now += 0.6
        source.events.append(TrackingTimeoutError("poll"))
        manager.step()
        assert manager.status.state == "tracking_lost"
        assert robot.hold_reason == "tracking_gap"


def test_callback_without_feedback_requires_an_explicit_reference(setup):
    source, config, _robot = setup
    commands = []
    callback = CallbackAdapter(commands.append, hold=lambda reason: None)
    with Teleoperator(source, robot=callback, config=config) as manager:
        with pytest.raises(TeleoperationError, match="RobotFeedback"):
            manager.arm()
        manager.arm(RobotFeedback(Pose(Vector3(0.3, 0, 0))))
        manager.step()
        assert commands[0].position.x == pytest.approx(0.31)


@pytest.mark.parametrize("operation", ["send", "read_feedback"])
def test_adapter_errors_latch_fault_preserve_cause_and_attempt_hold(setup, operation):
    source, config, robot = setup
    original = getattr(robot, operation)

    def fail(*args):
        raise OSError("Controller offline")

    with Teleoperator(source, robot=robot, config=config) as manager:
        manager.arm()
        setattr(robot, operation, fail)
        with pytest.raises(AdapterError, match="Controller offline") as caught:
            manager.step() if operation == "send" else manager._reference(None)
        assert isinstance(caught.value.__cause__, OSError)
        assert manager.status.state == "fault"
        assert robot.hold_reason == "adapter_fault"
        with pytest.raises(TeleoperationError, match="fault"):
            manager.arm()
        setattr(robot, operation, original)


def test_invalid_tracking_packet_holds_before_propagating_error(setup):
    source, config, robot = setup
    with Teleoperator(source, robot=robot, config=config) as manager:
        manager.arm()
        source.events.append(ValueError("Bad packet"))
        with pytest.raises(ValueError, match="Bad packet"):
            manager.step()
        assert manager.status.state == "fault"
        assert robot.hold_reason == "tracking_failed"


def test_health_failure_observed_after_read_prevents_target_delivery(setup):
    source, config, robot = setup
    with Teleoperator(source, robot=robot, config=config) as manager:
        manager.arm()
        source.health.status = "disconnected"
        assert manager.step() is None
        assert robot.targets_sent == 0
        assert manager.status.state == "tracking_lost"
        assert robot.hold_reason == "tracking_disconnected"


@pytest.mark.parametrize(
    "mode,age,status",
    [("sequential", 0.05, "streaming"), ("latest", 0.2, "streaming"), ("latest", 0.05, "closed")],
)
def test_incompatible_tracking_is_rejected_before_robot_open(setup, mode, age, status):
    source, config, robot = setup
    source.health.mode, source.health.status, source.max_frame_age = mode, status, age
    with pytest.raises(TeleoperationError):
        with Teleoperator(source, robot=robot, config=config):
            pass
    assert not robot._opened


def test_unsupported_adapter_capabilities_fail_before_open(setup):
    source, config, robot = setup
    robot.capabilities = RobotCapabilities(cartesian_position=False)
    with pytest.raises(TeleoperationError, match="kinematics"):
        with Teleoperator(source, robot=robot, config=config):
            pass
    assert not robot._opened


def test_partial_callback_startup_and_failed_hold_still_release_resources(setup):
    source, config, _robot = setup
    closed = []

    def failed_open():
        raise OSError("Startup failed")

    callback = CallbackAdapter(
        lambda target: None,
        hold=lambda reason: None,
        open=failed_open,
        close=lambda: closed.append(True),
    )
    with pytest.raises(AdapterError, match="Startup failed"):
        with Teleoperator(source, robot=callback, config=config):
            pass
    assert closed == [True]


def test_close_releases_adapter_even_when_hold_fails(setup):
    source, config, robot = setup
    manager = Teleoperator(source, robot=robot, config=config)
    manager.__enter__()

    def fail(reason):
        raise OSError("Hold failed")

    robot.hold = fail
    with pytest.raises(AdapterError, match="Hold failed"):
        manager.close()
    assert not robot._opened
