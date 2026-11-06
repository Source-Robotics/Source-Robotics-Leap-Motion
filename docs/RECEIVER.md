# Interpolated simulated receiver

> These additions are prepared for 0.1.0b4. Until that version is published, use a
> [source checkout](../CONTRIBUTING.md#set-up-a-source-checkout). PyPI currently provides b3.

Version **0.1.0b4** adds an optional simulated command receiver and independent gripper
filtering. The base install remains dependency-light. These components use the
standard library and the package's own geometry; no robot SDK or numerical toolbox
is required.

## Try it

```powershell
source-leap teleop --demo --interpolate
```

Remove `--demo` to use the connected Leap controller with simulated output. The
viewer starts disarmed. Arm and calibrate normally; its receiver indicator reports
the receiver state and accepted-command count. The viewport uses the interpolated
simulated feedback. Omitting `--interpolate` keeps immediate simulated feedback.

For a bounded run without opening a browser:

```powershell
source-leap teleop --demo --interpolate --headless --auto-arm --frames 60 --json
```

JSON adds a `receiver` status object; it is `null` for the immediate simulator.
The lab requests a 200 Hz receiver worker and a 40 ms interpolation horizon, with
workspace/speed bounds taken from the teleoperation configuration. This is a software
simulation, not a robot dynamics model or a real-time scheduling guarantee.

## Independent gripper filtering

The existing `[gripper]` TOML table accepts two optional settings:

```toml
[gripper]
source = "grab"
open_value = 1.0
closed_value = 0.0
max_speed = 1.0
deadband = 0.01
smoothing_time_constant = 0.12
max_output_hz = 30.0
```

Omit the new settings to retain the previous behavior: gripper smoothing inherits
`teleoperation.smoothing_time_constant`, and every emitted pose command can carry a
gripper value. A separate time constant changes gripper responsiveness independently
of position/orientation smoothing. A separate rate cap reduces gripper updates while
pose updates continue at their own cap. It must not exceed the total teleoperation
command-rate cap. Zero time constant disables smoothing; both frequency caps remain
upper bounds dependent on fresh frames, not fixed-rate guarantees.

Between gripper updates, `PoseTarget.gripper` is `None`, meaning no new gripper
setpoint. Speed limits use the elapsed time since the last gripper output. Calibration
and clutch re-anchoring reset both its reference and timing. The supplied simulated
receivers preserve existing gripper motion until its own command deadline; pose-only
packets do not extend that deadline. Choose a gripper cadence appropriate to command
lifetime; slower updates can intentionally leave held intervals between valid commands.

## Receiver contract

`CartesianReceiver` is a deterministic, transport-independent state machine. Call
`begin_session(session_id)` explicitly, then `accept(PoseTarget)` for incoming commands
and `advance()` from the receiving side's own loop. It retains one bounded interpolation
plan per channel rather than a FIFO of old targets. All time-dependent methods accept
an optional `now=` value from one monotonic clock for deterministic tests/replay.

- Session IDs identify new calibrations. Packets from other sessions are rejected.
- Sequence numbers must increase; rejected duplicates/out-of-order packets do not
  refresh expiry.
- Expiry uses local receipt time plus the smaller of `valid_for_s` and the configured
  `command_timeout`. Camera timestamps and wall clocks never extend that deadline.
- Interpolation starts from the current simulated pose, preserving continuity when
  replacing a target. Receiver workspace, linear/angular speed, and gripper speed
  bounds are enforced independently of sender-side checks.
- A delayed `advance()` samples motion at the expiry instant before holding; it does
  not move to the overdue target at the eventual tick time.
- Missing orientation/gripper fields leave their previous plans in place without
  refreshing those channels' own expiry. Position packets cannot keep an old gripper
  or rotation command valid indefinitely.
- Stream expiry latches. Ordinary packets cannot rearm it. A new explicit session is
  required. A deliberate clutch hold/resume can retain its session and sequence
  watermark; other holds require a new session.
- Invalid/regressed receiver time latches a fault; close/reopen is required.

The [expiry example](../examples/receiver_expiry.py) demonstrates this using explicit
clock values, without sleeping, starting threads, or opening devices:

```powershell
python examples/receiver_expiry.py
```

## Use the receiver with Teleoperator

`SimulatedReceiver` implements the robot adapter contract and owns one interpolation/
expiry worker. Construction/import starts no threads. `open()` starts its worker;
`close()` wakes and joins it. `read_feedback()` returns owned simulated feedback.
The worker continues to expire commands while the sending application is idle.

```python
from source_robotics_leap_motion import (
    Pose, ReceiverConfig, TeleoperationConfig, Teleoperator, Tracker,
)
from source_robotics_leap_motion.adapters import SimulatedReceiver

config = TeleoperationConfig.from_toml("examples/teleoperation.toml")
center = (config.workspace.minimum + config.workspace.maximum) * 0.5
robot = SimulatedReceiver(
    Pose(center),
    config=ReceiverConfig(
        workspace=config.workspace,
        max_linear_speed=config.max_linear_speed,
        max_angular_speed=config.max_angular_speed,
        max_gripper_speed=config.gripper.max_speed,
    ),
)

with Tracker.demo(mode="latest", max_frame_age=config.max_frame_age) as tracker:
    with Teleoperator(tracker, robot=robot, config=config) as teleop:
        teleop.arm()
        for _ in range(120):
            teleop.step()
```

Session-aware adapters declare `RobotCapabilities.command_sessions=True` and implement
`begin_session(session_id)`. `Teleoperator` calls it after explicit arm calibration
and after a requested clutch resume has received a fresh re-anchor frame. Existing
adapters default to `False` and keep their previous lifecycle.
`CallbackAdapter(..., begin_session=callback)` wraps this optional handshake.

This receiver supplies simulation and an integration boundary, not a network protocol
or hardware controller. A physical integration must run expiry/hold where it can
still act after the sending process or network disappears. The simulated worker
inside the sender process cannot supply that physical guarantee.

## Design reference

The separate robot-loop and gripper-filter ideas were informed by
[UltraGrasp](https://github.com/kvasios/ultragrasp/tree/3495255321b036b9bcaca99d06f4f7882991d8cf).
This implementation uses the existing package contracts and geometry; no UltraGrasp,
UMI, or Ultraleap binding code is bundled by this addition.

[Documentation index](README.md)
