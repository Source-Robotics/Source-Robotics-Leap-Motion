# Examples

Install the package first. Run these from the repository root using your source
venv's interpreter; [CONTRIBUTING.md](../CONTRIBUTING.md) shows setup without activation.

| File | Run or use | Input/output |
| --- | --- | --- |
| [read_hands.py](read_hands.py) | `python examples/read_hands.py --demo` | Ten synthetic frames; omit `--demo` for camera data |
| [latest_frames.py](latest_frames.py) | `python examples/latest_frames.py` | Live camera with a slower consumer and health diagnostics; stop with Ctrl+C |
| [custom_mapping.py](custom_mapping.py) | `python examples/custom_mapping.py` | Synthetic hand; prints mapped positions |
| [custom_robot.py](custom_robot.py) | `python examples/custom_robot.py --demo --duration 2` | Synthetic hand through callbacks to a simulated controller |
| [receiver_expiry.py](receiver_expiry.py) | `python examples/receiver_expiry.py` | Deterministic interpolation, command expiry, and explicit rearming; no hardware or threads |
| [my_arm.toml](my_arm.toml) | Used by `custom_mapping.py` | Signed axis mapping and position gains |
| [teleoperation.toml](teleoperation.toml) | `source-leap teleop --demo --config examples/teleoperation.toml` | Complete simulation workspace, mapping, speed, orientation, and gripper settings |

The runnable adapter example never connects to a physical robot. Replace its callbacks
with your controller SDK, units, feedback, and hold/expiry handling when integrating
an arm. See [teleoperation](../docs/TELEOPERATION.md) and [API usage](../docs/USAGE.md).
The [receiver guide](../docs/RECEIVER.md) explains `source-leap teleop --demo --interpolate`.
