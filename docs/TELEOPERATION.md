**Generic teleoperation — 0.1.0b3 development**

The package now includes relative Cartesian control, a synchronous adapter contract,
and a browser lab with a simulated output. The lab is bundled with the Python package
and needs no web framework, numerical toolbox, robot SDK, or JavaScript build step.

```powershell
.\.venv\Scripts\source-leap.exe teleop --demo
.\.venv\Scripts\source-leap.exe teleop
.\.venv\Scripts\source-leap.exe teleop --demo --config examples\teleoperation.toml
```

The first command uses a synthetic hand. The second uses the Leap controller. Both
send targets exclusively to `SimulatedArm`, which supplies immediate Cartesian
feedback. The viewer shows a workspace, tool position/orientation, recent path,
normalized gripper openness, frame rate, and local tracking age. It is a target
visualizer, with no robot joint geometry, inverse kinematics, collisions, or dynamics.

Click **Arm & calibrate** with the selected hand visible. Move the hand to move the
tool target. Click **Clutch** to hold output while repositioning, then **Resume** to
capture the new hand reference. Holding Space also clutches; Escape disarms. Losing
focus while holding Space disarms. Hand loss requires explicit rearming. Reconnect
tracking explicitly after a device/service disconnect, then arm again.

`--no-browser` prints the loopback URL without opening it. `--duration` and `--frames`
bound a run. `--headless --json` prints lab telemetry; `--auto-arm` explicitly requests
one initial simulated-arm calibration. It never rearms after loss. `--replay PATH`
uses recorded timing and does not need the controller. Default CLI bounds and speeds
belong to the simulation; a custom integration must supply its own configuration.

**API and ownership.** The application owns a latest-mode `Tracker`; `Teleoperator`
owns the adapter inside its context. Controller and adapter methods run on the calling
application thread. Tracking acquisition keeps its separate owning worker. No robot
connection or additional thread is created by import or configuration construction.

```python
from source_robotics_leap_motion import Pose, TeleoperationConfig, Teleoperator, Tracker, Vector3
from source_robotics_leap_motion.adapters import SimulatedArm

config = TeleoperationConfig.from_toml("examples/teleoperation.toml")
robot = SimulatedArm(Pose(Vector3(0.3, 0.0, 0.3)))

with Tracker.demo(mode="latest", max_frame_age=config.max_frame_age) as tracker:
    with Teleoperator(tracker, robot=robot, config=config) as teleop:
        teleop.arm()
        for _ in range(120):
            teleop.step()
```

Use `CallbackAdapter(send=..., hold=..., feedback=..., open=..., close=...)` to wrap
an existing SDK. `send` receives an immutable `PoseTarget`. `hold(reason)` is mandatory
and must cancel or hold motion through that controller's interface. `feedback` returns
`RobotFeedback(Pose(...), gripper=...)`. Without feedback, pass an explicit known
reference to `arm(reference)` and `release_clutch(reference)`. Orientation/gripper
capabilities default to false and must be declared when implemented. Unsupported
configured commands are rejected before opening the adapter.

The runnable [callback example](../examples/custom_robot.py) wraps the simulated
controller through these exact callbacks. Replacing that boundary is the integration
work for an arm. Cartesian controllers can accept mapped poses directly after unit
conversion. Joint-only controllers need kinematics and joint limits in their adapter
or robotics stack. The core implements Cartesian pose output; velocity/joint output
modes, SDK-specific adapters, and a network receiver are future additions.

**Commands and conventions.** Positions and bounds use metres, linear speed uses
metres/second, and angular speed uses radians/second. `orientation=None` leaves
orientation to the controller; `gripper=None` leaves the gripper to the controller.
Enabled gripper commands and feedback are normalized to [0, 1]; the adapter converts
them to its own actuator units. Initial gripper feedback/reference is required when
gripper control is enabled.

Commands include a random calibration session ID, increasing sequence, source frame
ID/timestamp/clock domain, and `valid_for_s`. A receiver uses its own monotonic receipt
clock to expire commands. Source timestamps do not synchronize machines. Adapters
must bound blocking SDK operations; application polling cannot stop a robot after
the application or network disappears. Implement expiry/hold in the receiving
controller and retain its own motion/limit enforcement.

**Control behavior.**

| State | Output and transition |
| --- | --- |
| `disarmed` | No target commands. Explicit arm calibrates one selected hand against supplied robot feedback/reference. |
| `active` | Distinct fresh hand frames can produce bounded targets. Arm itself emits no target. |
| `clutched` | Hold invoked; no target commands. Resume waits for a fresh frame, re-anchors to the supplied held robot reference, and emits nothing on that re-anchor frame. |
| `tracking_lost` | Hold invoked once on the loss transition. Returning frames do not rearm. |
| `fault` | Adapter/control error latched. Close and reopen before rearming. |
| `closed` | Hold and adapter close attempted; tracker ownership stays with the application. |

Loss triggers include missing/ambiguous selected hands, hand identity changes, stale
local age, local update gaps, non-advancing/regressing source timestamps, source time
gaps, device changes, and clock-domain changes. Duplicates produce no output and do
not extend the tracking deadline. Empty-hand frames still mean the camera streams;
they also cause hand-based control to hold. Adapter exceptions preserve their original
cause; a failed send attempts hold before surfacing `AdapterError`.

Position mapping is `robot_reference + gain * R * (hand - hand_reference)`, using
the configured proper axis rotation `R`. Each update clamps the desired position to
the workspace, smooths toward it, then bounds the norm of the target increment by
`max_linear_speed * elapsed`. Deadband uses the unsmoothed position error. This
limits commanded Cartesian targets; it does not model the robot's physical motion.

`mapping.rotation` is an optional normalized x/y/z/w quaternion for arbitrary frame
alignment. It applies after signed axis assignment; gains apply in robot axes after
that rotation. The total `R` is used for position and orientation mapping together.
Its default is identity, preserving existing axis/gain-only configurations.

Optional rotation mapping uses world-frame relative rotation:
`delta = q_hand * inverse(q_hand_reference)` and
`q_target = R * delta**rotation_gain * inverse(R) * q_robot_reference`.
The multiplication convention applies the rightmost rotation first, as documented
for [rotation composition](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.transform.Rotation.__mul__.html).
Quaternion smoothing follows the shortest rotation path using
[spherical interpolation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.transform.Slerp.html),
then caps the commanded angular increment. The implementation uses standard-library
math and has no SciPy dependency. Exponential smoothing uses elapsed local time and
`alpha = 1 - exp(-elapsed / time_constant)`. Zero time constant disables it.

The output frequency is a maximum, not a periodic-delivery guarantee. Filtering and
speed history reset on calibration and clutch re-anchoring. Configured hand/clock
changes and long gaps require a new calibration. The control engine retains one
accepted frame, one hand anchor, and one command. Latest acquisition has one pending
frame; the lab retains the latest observed frame and a 240-point browser path.

**Validation.** Tests cover calibration, configured axes/gains, no-output states,
tracking and identity loss, duplicate deadlines, clutch continuity, workspace/speed
bounds over a 500-frame trajectory, quaternion composition, angular limits, gripper
mapping, smoothing, command rate caps, adapter capabilities/failures/cleanup, strict
configuration, CLI telemetry, and packaged local HTTP assets/actions. Actual robot
motion and clean-PC driver installation remain separate hardware validation work.

On Windows, the installed b3 wheel passed **180 tests on each of Python 3.10.11,
3.11.9, 3.12.10, 3.13.17, 3.14.10, and 3.15.2**. Each environment received 30 live
sequential frames and 30 latest-mode frames. The previously recorded 1,047-frame
session, containing 50 complete left-hand samples, generated 18 simulated targets
through a clutch/resume cycle. All targets stayed within the configured workspace
and speed bounds, and hand loss produced no further commands. Wheel metadata,
dependency checks, CLI examples, and the bundled viewer assets were also checked.
Chrome UI checks exercised calibration, target movement, clutch hold, and resume.
Raw local evidence is in `.tools/compatibility-results-0.1.0b3.json` and
`.tools/control-recording-b3.json`. No physical robot has been commanded.
