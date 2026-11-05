import math

import pytest

from source_robotics_leap_motion import Mapping, Quaternion, Vector3


def test_arbitrary_frame_rotation_precedes_robot_axis_gains():
    # Rotate 45 degrees around z, then scale the robot x axis by two.
    mapping = Mapping(
        rotation=Quaternion(0, 0, math.sin(math.pi / 8), math.cos(math.pi / 8)),
        gain=Vector3(2, 1, 1),
    )
    point = mapping.map_position(Vector3(1, 0, 0))
    assert tuple(point) == pytest.approx((math.sqrt(2), math.sqrt(0.5), 0))


def test_mapping_toml_supports_explicit_quaternion_rotation(tmp_path):
    path = tmp_path / "rotation.toml"
    path.write_text("[mapping]\nrotation = [0.0, 0.0, 1.0, 0.0]\n", encoding="utf-8")
    assert Mapping.from_toml(path).map_position(Vector3(1, 0, 0)).x == pytest.approx(-1)


def test_mapping_preserves_calibrated_robot_origin_and_relative_axes():
    mapping = Mapping(axes=("-z", "-x", "y"), gain=Vector3(0.5, 0.5, 0.5))
    hand_origin = Vector3(0.01, 0.25, 0.02)
    robot_origin = Vector3(0.2, 0, 0.2)
    assert (
        mapping.map_position(hand_origin, hand_origin=hand_origin, robot_origin=robot_origin)
        == robot_origin
    )
    target = mapping.map_position(
        hand_origin + Vector3(0.02, 0.04, -0.06),
        hand_origin=hand_origin,
        robot_origin=robot_origin,
    )
    assert tuple(target) == pytest.approx((0.23, -0.01, 0.22))


def test_axis_lock_and_independent_gains():
    mapping = Mapping(gain=Vector3(0, 0.5, 2))
    assert mapping.map_position(Vector3(1, 2, 3)) == Vector3(0, 1, 6)


@pytest.mark.parametrize("axes", [("x", "x", "z"), ("-x", "y", "z"), ("--x", "y", "z")])
def test_invalid_or_reflecting_coordinate_frames_are_rejected(axes):
    with pytest.raises(ValueError):
        Mapping(axes=axes)


def test_unknown_config_setting_is_not_silently_ignored(tmp_path):
    path = tmp_path / "arm.toml"
    path.write_text("[mapping]\ngian = [1, 1, 1]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="gian"):
        Mapping.from_toml(path)
