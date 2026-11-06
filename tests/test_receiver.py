import math
from dataclasses import replace

import pytest

from source_robotics_leap_motion import (
    CartesianReceiver,
    Pose,
    PoseTarget,
    Quaternion,
    ReceiverConfig,
    RobotFeedback,
    Vector3,
    Workspace,
)
from source_robotics_leap_motion._geometry import angle


def config(**overrides):
    values = dict(
        workspace=Workspace(Vector3(-2, -2, -2), Vector3(2, 2, 2)),
        max_linear_speed=1,
        max_angular_speed=1,
        max_gripper_speed=1,
        interpolation_time=0.1,
        command_timeout=0.5,
    )
    values.update(overrides)
    return ReceiverConfig(**values)


def receiver(**overrides):
    return CartesianReceiver(RobotFeedback(Pose(Vector3()), 1.0), config=config(**overrides))


def target(sequence=1, *, position=None, session="one", ttl=0.5, orientation=None, gripper=None):
    position = Vector3(1, 0, 0) if position is None else position
    return PoseTarget(position, orientation, gripper, session, sequence, 10, 1_000, "camera", ttl)


def test_session_handshake_is_explicit_and_commands_never_arm_a_receiver():
    rx = receiver()
    assert not rx.accept(target(), now=0)
    assert rx.feedback.pose.position == Vector3()
    rx.begin_session("one", now=0)
    assert rx.status.state == "armed"
    assert not rx.accept(target(session="other"), now=0)
    assert rx.accept(target(), now=0)
    assert rx.status.accepted_commands == 1


def test_interpolation_is_continuous_when_a_new_target_replaces_the_old_one():
    rx = receiver(max_linear_speed=10)
    rx.begin_session("one", now=0)
    rx.accept(target(), now=0)
    before = rx.advance(now=0.04)
    assert before.pose.position.x == pytest.approx(0.4)
    assert rx.accept(target(2, position=Vector3(-0.5, 0, 0)), now=0.04)
    assert rx.feedback == before
    assert rx.advance(now=0.09).pose.position.x == pytest.approx(-0.05)
    assert before.pose.position.x == pytest.approx(0.4)  # Owned feedback remains unchanged.


def test_delayed_tick_stops_at_the_expiry_instant_not_the_eventual_tick_time():
    rx = receiver(max_linear_speed=0.2)
    rx.begin_session("one", now=0)
    rx.accept(target(ttl=0.1), now=0)
    result = rx.advance(now=10)
    assert result.pose.position.x == pytest.approx(0.02)
    assert rx.status.state == "expired"
    assert not rx.accept(target(2), now=10)
    with pytest.raises(ValueError, match="new session"):
        rx.begin_session("one", now=10)
    rx.begin_session("two", now=10)
    assert not rx.accept(target(3, session="one"), now=10)
    assert rx.accept(target(1, session="two"), now=10)


def test_duplicates_and_out_of_order_commands_do_not_refresh_expiry():
    rx = receiver()
    rx.begin_session("one", now=0)
    rx.accept(target(5, ttl=0.1), now=0)
    for index, sequence in enumerate((5, 3, 0), start=1):
        assert not rx.accept(target(sequence), now=index * 0.02)
    rx.advance(now=0.1)
    assert rx.status.state == "expired"
    assert rx.status.sequence == 5
    assert rx.status.rejected_commands == 3


def test_source_clocks_cannot_extend_the_local_timeout_cap():
    rx = receiver(command_timeout=0.2)
    rx.begin_session("one", now=5)
    command = replace(target(ttl=1000), source_timestamp_us=10**20, clock_domain="remote-future")
    assert rx.accept(command, now=5)
    assert rx.advance(now=5.2).pose.position.x == pytest.approx(0.2)
    assert rx.status.state == "expired"


def test_no_first_command_also_expires_and_holds_the_initial_pose():
    rx = receiver(command_timeout=0.2)
    rx.begin_session("one", now=0)
    assert rx.advance(now=0.2).pose.position == Vector3()
    assert rx.status.state == "expired"
    assert not rx.accept(target(), now=0.2)


def test_clutch_holds_and_explicit_resume_keeps_the_sequence_watermark():
    rx = receiver()
    rx.begin_session("one", now=0)
    rx.accept(target(5), now=0)
    rx.hold("clutched", now=0.03)
    held = rx.feedback
    rx.hold("clutched", now=0.04)  # Repeating a hold is idempotent.
    assert rx.advance(now=8) == held
    assert not rx.accept(target(6), now=8)
    rx.begin_session("one", after_sequence=5, now=8)
    assert not rx.accept(target(5), now=8)
    assert rx.accept(target(6), now=8)
    rx.hold("hand_missing", now=8.01)
    with pytest.raises(ValueError, match="new session"):
        rx.begin_session("one", now=8.01)


def test_resume_rejects_unseen_packets_sent_before_clutching():
    rx = receiver()
    rx.begin_session("one", now=0)
    rx.accept(target(5), now=0)
    rx.hold("clutched", now=0.03)
    with pytest.raises(ValueError, match="watermark"):
        rx.begin_session("one", now=0.04)
    with pytest.raises(ValueError, match="watermark"):
        rx.begin_session("one", after_sequence=4, now=0.04)
    # The sender had produced commands through #10, even though only #5 arrived.
    rx.begin_session("one", after_sequence=10, now=0.04)
    assert not rx.accept(target(9), now=0.04)
    assert not rx.accept(target(10), now=0.04)
    assert rx.accept(target(11), now=0.04)


def test_pose_only_updates_preserve_gripper_and_rotation_plans_without_refreshing_them():
    rx = receiver()
    rx.begin_session("one", now=0)
    rotation = Quaternion(0, 0, math.sin(0.5), math.cos(0.5))
    rx.accept(target(orientation=rotation, gripper=0, ttl=0.1), now=0)
    rx.accept(target(2, ttl=0.5), now=0.05)
    assert rx.advance(now=0.075).gripper == pytest.approx(0.925)
    result = rx.advance(now=0.2)
    assert rx.status.state == "active"
    assert result.gripper == pytest.approx(0.9)
    assert angle(Quaternion(), result.pose.orientation) == pytest.approx(0.1)
    assert result.pose.position.x == pytest.approx(0.2)


def test_each_channel_obeys_its_speed_limit_with_jitter_and_replacement():
    rx = receiver(max_linear_speed=0.2, max_angular_speed=0.5, max_gripper_speed=0.3)
    rx.begin_session("one", now=0)
    rx.accept(target(orientation=Quaternion(0, 0, 1, 0), gripper=0), now=0)
    previous, previous_time = rx.feedback, 0.0
    for index in range(1, 81):
        now = index * 0.005
        current = rx.advance(now=now)
        dt = now - previous_time
        assert (current.pose.position - previous.pose.position).norm <= 0.2 * dt + 1e-12
        assert angle(previous.pose.orientation, current.pose.orientation) <= 0.5 * dt + 1e-9
        assert abs(current.gripper - previous.gripper) <= 0.3 * dt + 1e-12
        assert rx.config.workspace.contains(current.pose.position)
        if index % 7 == 0:
            rx.accept(target(index, position=Vector3(-1, 1, 0)), now=now)
        previous, previous_time = current, now


@pytest.mark.parametrize(
    "changes",
    [
        {"sequence": True},
        {"sequence": 1.5},
        {"valid_for_s": float("nan")},
        {"valid_for_s": float("inf")},
        {"valid_for_s": 0},
        {"valid_for_s": True},
        {"position": None},
        {"orientation": "invalid"},
        {"gripper": float("nan")},
        {"gripper": 2},
        {"gripper": True},
        {"source_frame_id": -1},
        {"source_timestamp_us": -1},
        {"clock_domain": ""},
    ],
)
def test_invalid_packets_do_not_move_or_refresh_the_receiver(changes):
    rx = receiver()
    rx.begin_session("one", now=0)
    assert not rx.accept(replace(target(), **changes), now=0)
    assert rx.status.accepted_commands == 0
    assert rx.advance(now=0.5).pose.position == Vector3()
    assert rx.status.state == "expired"


def test_workspace_and_missing_gripper_reference_are_receiver_side_checks():
    rx = CartesianReceiver(RobotFeedback(Pose(Vector3())), config=config())
    rx.begin_session("one", now=0)
    assert not rx.accept(target(position=Vector3(3, 0, 0)), now=0)
    assert rx.status.last_rejection == "outside_workspace"
    assert not rx.accept(target(gripper=0), now=0)
    assert rx.status.last_rejection == "missing_gripper_reference"
    assert rx.accept(target(), now=0)


@pytest.mark.parametrize("now", [-1, float("nan"), float("inf"), True])
def test_invalid_receiver_clock_latches_a_fault(now):
    rx = receiver()
    rx.begin_session("one", now=0)
    with pytest.raises(ValueError):
        rx.advance(now=now)
    assert rx.status.state == "fault"
    with pytest.raises(ValueError, match="Reopen"):
        rx.begin_session("two", now=1)


def test_regressed_clock_faults_and_close_cancels_all_motion():
    rx = receiver()
    rx.begin_session("one", now=1)
    rx.accept(target(), now=1)
    feedback = rx.advance(now=1.02)
    with pytest.raises(ValueError, match="backwards"):
        rx.advance(now=1.01)
    assert rx.advance(now=2) == feedback
    rx.close(now=2)
    assert rx.advance(now=3) == feedback
    assert rx.status.state == "closed"
    with pytest.raises(ValueError, match="Reopen"):
        rx.begin_session("two", now=3)


@pytest.mark.parametrize(
    "settings",
    [
        {"max_linear_speed": 0},
        {"max_angular_speed": float("nan")},
        {"max_gripper_speed": True},
        {"command_timeout": 0},
        {"interpolation_time": -1},
        {"interpolation_time": 1},
    ],
)
def test_invalid_receiver_configuration_is_rejected(settings):
    with pytest.raises(ValueError):
        config(**settings)
