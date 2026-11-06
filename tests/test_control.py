import math
from dataclasses import replace

import pytest

from source_robotics_leap_motion import (
    Frame,
    GripperMapping,
    Hand,
    Mapping,
    Palm,
    Pose,
    Quaternion,
    RobotFeedback,
    TeleoperationConfig,
    TeleoperationController,
    TeleoperationError,
    Vector3,
    Workspace,
)


def config(**values):
    defaults = dict(
        workspace=Workspace(Vector3(-1, -1, -1), Vector3(1, 1, 1)),
        max_linear_speed=100,
        max_angular_speed=100,
        smoothing_time_constant=0,
        position_deadband=0,
        max_output_hz=1000,
        tracking_timeout=0.5,
    )
    defaults.update(values)
    return TeleoperationConfig(**defaults)


def frame(
    index=0,
    position=None,
    *,
    orientation=None,
    hand_id=1,
    hands=True,
    timestamp=None,
    grab=0,
    pinch=0,
):
    hand = Hand(
        hand_id,
        "right",
        Palm(position or Vector3(), orientation or Quaternion()),
        grab_strength=grab,
        pinch_strength=pinch,
    )
    return Frame(
        index, index * 100_000 if timestamp is None else timestamp, (hand,) if hands else ()
    )


def armed(**values):
    controller = TeleoperationController(config(**values))
    controller.arm(frame(), RobotFeedback(Pose(Vector3()), 1.0), now=0)
    return controller


def test_disarmed_controller_never_emits_and_arm_does_not_emit():
    controller = TeleoperationController(config())
    assert controller.update(frame(), now=0) is None
    controller.arm(frame(), RobotFeedback(Pose(Vector3())), now=0)
    assert controller.status.last_target is None
    assert controller.update(frame(), now=0.01) is None
    assert controller.update(frame(1, Vector3(0.1, 0, 0)), now=0.1).position.x == 0.1


def test_relative_calibration_preserves_robot_pose_and_configured_axes():
    controller = TeleoperationController(
        config(mapping=Mapping(("-z", "-x", "y"), Vector3(0.5, 0, 2)))
    )
    controller.arm(
        frame(position=Vector3(0, 0.3, 0)), RobotFeedback(Pose(Vector3(0.2, 0.1, 0.2))), now=0
    )
    target = controller.update(frame(1, Vector3(0.1, 0.4, -0.2)), now=0.1)
    assert tuple(target.position) == pytest.approx((0.3, 0.1, 0.4))
    assert target.orientation is None and target.gripper is None
    assert target.sequence == 1 and target.source_frame_id == 1


@pytest.mark.parametrize(
    "failure",
    [
        "missing",
        "hand_changed",
        "clock",
        "device",
        "rewind",
        "frozen_clock",
        "source_gap",
        "local_gap",
        "stale",
    ],
)
@pytest.mark.parametrize("clutched", [False, True])
def test_tracking_failures_latch_and_fresh_frames_do_not_rearm(failure, clutched):
    controller = armed()
    if failure == "rewind":
        controller.disarm()
        controller.arm(frame(timestamp=200_000), RobotFeedback(Pose(Vector3())), now=0)
    if clutched:
        controller.clutch()
    candidate = frame(1)
    now, age = 0.1, 0
    if failure == "missing":
        candidate = frame(1, hands=False)
    elif failure == "hand_changed":
        candidate = frame(1, hand_id=2)
    elif failure == "clock":
        candidate = replace(candidate, clock_domain="other")
    elif failure == "device":
        candidate = replace(candidate, device_id=2)
    elif failure == "frozen_clock":
        candidate = frame(1, timestamp=0)
    elif failure == "source_gap":
        candidate = frame(1, timestamp=600_000)
    elif failure == "local_gap":
        now = 0.6
    elif failure == "stale":
        age = 0.11
    assert controller.update(candidate, now=now, frame_age=age) is None
    assert controller.status.state == "tracking_lost"
    assert controller.update(frame(2), now=0.7) is None
    assert controller.status.state == "tracking_lost"


def test_duplicates_do_not_extend_tracking_deadline_and_explicit_rearm_changes_session():
    controller = armed()
    session = controller.status.session_id
    for now in (0.1, 0.3, 0.6):
        assert controller.update(frame(), now=now) is None
    assert controller.status.state == "tracking_lost"
    controller.arm(frame(10), RobotFeedback(Pose(Vector3())), now=0.7)
    assert controller.status.session_id != session
    assert controller.status.sequence == 0


def test_clutch_holds_and_reanchors_without_position_or_rotation_jump():
    controller = armed(control_orientation=True)
    first = controller.update(frame(1, Vector3(0.1, 0, 0)), now=0.1)
    controller.clutch()
    assert controller.update(frame(2, Vector3(0.8, 0, 0)), now=0.2) is None
    controller.release_clutch(RobotFeedback(Pose(first.position)))
    assert controller.update(frame(3, Vector3(0.9, 0, 0)), now=0.3) is None
    assert controller.status.state == "active"
    target = controller.update(frame(4, Vector3(1, 0, 0)), now=0.4)
    assert target.position.x == pytest.approx(0.2)
    assert target.sequence == 2


def test_workspace_and_vector_speed_limit_hold_over_a_long_trajectory():
    bounds = Workspace(Vector3(-0.2, -0.2, -0.2), Vector3(0.2, 0.2, 0.2))
    controller = armed(workspace=bounds, max_linear_speed=0.2)
    previous = Vector3()
    for index in range(1, 501):
        t = index / 100
        target = controller.update(
            frame(index, Vector3(math.sin(t) * 2, 2, math.cos(t) * 2), timestamp=index * 10_000),
            now=t,
        )
        assert bounds.contains(target.position)
        assert (target.position - previous).norm <= 0.002 + 1e-12
        previous = target.position
    assert controller.status.workspace_limited


def test_smoothing_is_time_based_and_deadband_applies_before_smoothing():
    controller = armed(smoothing_time_constant=0.1, position_deadband=0.001)
    target = controller.update(frame(1, Vector3(0.01, 0, 0)), now=0.1)
    assert target.position.x == pytest.approx(0.01 * (1 - math.exp(-1)))
    before = target.position
    target = controller.update(frame(2, before + Vector3(0.0005, 0, 0)), now=0.2)
    assert target.position == before


def test_relative_orientation_is_mapped_in_robot_axes_and_composed_in_world_order():
    root_half = math.sqrt(0.5)
    controller = TeleoperationController(
        config(control_orientation=True, mapping=Mapping(("-z", "-x", "y")))
    )
    controller.arm(
        frame(), RobotFeedback(Pose(Vector3(), Quaternion(0, root_half, 0, root_half))), now=0
    )
    target = controller.update(
        frame(1, orientation=Quaternion(0, 0, root_half, root_half)), now=0.1
    )
    q = target.orientation
    assert (q.x, q.y, q.z, q.w) == pytest.approx((-0.5, 0.5, -0.5, 0.5))


def test_rotation_gain_and_angular_speed_are_limited():
    controller = armed(control_orientation=True, max_angular_speed=1, rotation_gain=0.5)
    target = controller.update(frame(1, orientation=Quaternion(0, 0, 1, 0)), now=0.1)
    assert target.orientation.z == pytest.approx(math.sin(0.05))
    assert target.orientation.w == pytest.approx(math.cos(0.05))
    assert controller.status.speed_limited


def test_extra_frame_rotation_applies_to_position_and_orientation_together():
    s = math.sqrt(0.5)
    controller = armed(control_orientation=True, mapping=Mapping(rotation=Quaternion(0, 0, s, s)))
    target = controller.update(
        frame(1, Vector3(0.1, 0, 0), orientation=Quaternion(s, 0, 0, s)), now=0.1
    )
    assert tuple(target.position) == pytest.approx((0, 0.1, 0))
    q = target.orientation
    assert (q.x, q.y, q.z, q.w) == pytest.approx((0, s, 0, s))


def test_gripper_mapping_limits_speed_and_holds_during_clutch():
    controller = armed(gripper=GripperMapping(source="pinch", max_speed=0.5, deadband=0))
    target = controller.update(frame(1, pinch=1), now=0.1)
    assert target.gripper == pytest.approx(0.95)
    controller.clutch()
    assert controller.update(frame(2, pinch=0), now=0.2) is None
    assert controller.status.last_target.gripper == pytest.approx(0.95)


def test_output_frequency_is_a_cap_and_skipped_inputs_still_refresh_tracking():
    controller = armed(max_output_hz=10)
    for index in range(1, 10):
        assert controller.update(frame(index, timestamp=index * 10_000), now=index / 100) is None
    assert controller.update(frame(10, timestamp=100_000), now=0.1).sequence == 1


@pytest.mark.parametrize(
    "reference,frame_age",
    [
        (RobotFeedback(Pose(Vector3(2, 0, 0))), 0),
        (RobotFeedback(Pose(Vector3())), 0.11),
    ],
)
def test_invalid_calibration_stays_disarmed(reference, frame_age):
    controller = TeleoperationController(config())
    with pytest.raises(TeleoperationError):
        controller.arm(frame(), reference, now=0, frame_age=frame_age)
    assert controller.status.state == "disarmed"


def test_gripper_requires_known_reference_and_missing_hand_cannot_calibrate():
    controller = TeleoperationController(config(gripper=GripperMapping()))
    with pytest.raises(TeleoperationError, match="gripper reference"):
        controller.arm(frame(), RobotFeedback(Pose(Vector3())), now=0)
    with pytest.raises(TeleoperationError, match="exactly one"):
        controller.arm(frame(hands=False), RobotFeedback(Pose(Vector3()), 1), now=0)


def test_local_clock_regression_faults_and_cannot_rearm_without_new_controller():
    controller = armed()
    controller.update(frame(1), now=0.1)
    with pytest.raises(TeleoperationError, match="backwards"):
        controller.update(frame(2), now=0.05)
    assert controller.status.state == "fault"
    controller.disarm()
    with pytest.raises(TeleoperationError):
        controller.arm(frame(2), RobotFeedback(Pose(Vector3())), now=0.2)
