import pytest

from source_robotics_leap_motion import GripperMapping, TeleoperationConfig, Vector3, Workspace


@pytest.mark.parametrize(
    "values",
    [
        {"max_linear_speed": 0},
        {"max_linear_speed": float("nan")},
        {"max_linear_speed": True},
        {"smoothing_time_constant": -1},
        {"position_deadband": -1},
        {"max_frame_age": 0.2},
        {"max_output_hz": 1001},
        {"handedness": "both"},
        {"control_orientation": "true"},
    ],
)
def test_invalid_settings_are_rejected(values):
    settings = {"workspace": Workspace(Vector3(), Vector3(1, 1, 1)), "max_linear_speed": 1}
    settings.update(values)
    with pytest.raises(ValueError):
        TeleoperationConfig(**settings)


def test_workspace_rejects_inverted_bounds():
    with pytest.raises(ValueError, match="minimum"):
        Workspace(Vector3(1, 0, 0), Vector3())


@pytest.mark.parametrize(
    "settings",
    [{"source": "fist"}, {"max_speed": 0}, {"open_value": 1.1}, {"closed_value": float("nan")}],
)
def test_invalid_gripper_settings(settings):
    with pytest.raises(ValueError):
        GripperMapping(**settings)


def test_toml_configuration_and_typo_rejection(tmp_path):
    path = tmp_path / "arm.toml"
    text = """[workspace]
minimum = [0, -0.3, 0]
maximum = [0.6, 0.3, 0.6]
[mapping]
axes = ["-z", "-x", "y"]
gain = [0.5, 0.5, 0.5]
[teleoperation]
max_linear_speed = 0.2
control_orientation = true
[gripper]
source = "pinch"
"""
    path.write_text(text, encoding="utf-8")
    config = TeleoperationConfig.from_toml(path)
    assert config.mapping.axes == ("-z", "-x", "y")
    assert config.gripper.source == "pinch"
    assert config.control_orientation
    path.write_text(text.replace("max_linear_speed", "max_linear_speeed"), encoding="utf-8")
    with pytest.raises(ValueError, match="max_linear_speed"):
        TeleoperationConfig.from_toml(path)
