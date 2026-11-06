# Python API and command-line usage

## Read hand data

The same API accepts live, synthetic, and replay sources:

```python
from source_robotics_leap_motion import Tracker

with Tracker() as tracker:  # use Tracker.demo() to try without a camera
    print("Backend:", tracker.backend_name)
    for frame in tracker:
        if hand := frame.right_hand:
            print(hand.palm.position, hand.grab_strength)
```

Positions, widths, and distances use **metres**; palm velocity uses metres/second.
Camera axes remain Leap's axes: +x right, +y up, +z toward the user. Quaternions have
named `x`, `y`, `z`, `w` components. Frame timestamps are microseconds in the named
`clock_domain`, not Unix time. An empty-hand frame is valid; absence of frames produces
`TrackingTimeoutError`. Service/camera disconnections produce `ConnectionError`.

Frames are immutable Python snapshots and retain no SDK pointers. LeapC includes
finger/arm rotations. The legacy backend exposes finger joint positions when supplied
by protocol v6, derives palm orientation from normal/direction, and reports unavailable
bone rotations and pinch distance as `None`. It never substitutes a made-up rotation.

## Latest frames and health

 A slow application can request
the newest unread frame instead of falling behind the camera stream:

```python
from source_robotics_leap_motion import Tracker

with Tracker(mode="latest", max_frame_age=0.1) as tracker:
    frame = tracker.read(timeout=0.25)
    print(frame.right_hand)
    print(tracker.health.to_dict())
```

One background thread owns the source and replaces a single pending frame. Skipped
frames are counted. Reads wait for a new frame and never repeat a consumed frame.
An unread frame older than `max_frame_age` is discarded; if no fresh frame arrives
before the read deadline, `StaleFrameError` (a `TrackingTimeoutError`) is raised.
The default remains sequential, which is appropriate when recording every frame.

`tracker.health` reports connection state, recent received FPS, local frame age,
received/delivered/skipped/duplicate counts, timeouts, timestamp resets, and hand
count. No hands still means the camera is streaming. Age is measured **since Python
received the frame**, not end-to-end camera latency. It cannot detect every delay
inside a service or transport. See [semantics and validation](https://github.com/Source-Robotics/Source-Robotics-Leap-Motion/blob/main/docs/LATEST_FRAMES.md).

```powershell
source-leap --latest --health --duration 10
source-leap --demo --latest --health --frames 60 --json
```

Health JSON goes to stderr; frame JSON on stdout and the recording schema are unchanged.

## Record and replay

 Existing recordings are protected by default:

```powershell
source-leap record recordings\session.jsonl --frames 300
source-leap replay recordings\session.jsonl --realtime
source-leap record recordings\demo.jsonl --demo --frames 60
source-leap replay recordings\demo.jsonl --json
```

The destination folder is created automatically. JSON output contains only frames on stdout;
status and errors go to stderr. Each recording has a schema version, timestamp and
coordinate conventions, and one frame per line. Reading streams the file without
loading the whole session. Headerless historical `motion_data.txt` files use a different
format and are not accepted as recordings.

```python
from source_robotics_leap_motion import Recorder, Tracker, read_recording

with Tracker.demo(realtime=False) as tracker, Recorder("demo.jsonl") as recording:
    for _ in range(60):
        recording.write(tracker.read())

for frame in read_recording("demo.jsonl"):
    print(frame.timestamp_us, frame.right_hand.palm.position)
```

## Customize coordinate mapping

 The package provides a pure mapping function, with
no hard-coded robot origin or workspace:

```python
from source_robotics_leap_motion import Mapping, Vector3

mapping = Mapping(axes=("-z", "-x", "y"), gain=Vector3(0.5, 0.5, 0.5))
target = mapping.map_position(
    hand.palm.position,
    hand_origin=calibrated_hand_position,
    robot_origin=current_robot_position,
)
```

Gains apply in output coordinates. Zero locks an axis. Signed axis permutations must
preserve handedness. `Mapping.from_toml("examples/my_arm.toml")` loads the same settings.
From a source checkout, run `python examples/custom_mapping.py` for a complete synthetic example that only
prints targets.


## Teleoperation and adapters

`source-leap teleop` uses the connected controller with simulated robot output;
`source-leap teleop --demo` also simulates the hand. Configuration and calibration,
clutch behavior, workspace/speed limits, and the callback adapter contract are
documented in [the teleoperation guide](TELEOPERATION.md). The runnable
[custom controller example](../examples/custom_robot.py) wraps a simulated controller.

## Diagnostics

`source-leap doctor` inspects fixed runtime locations without loading native code.
`source-leap doctor --probe` also opens tracking and waits for a frame. Exit code 0
means the requested check passed, 2 means a configuration/tracking error, and Ctrl+C
returns 130. A connected WebSocket alone does not prove that the camera is streaming.

```powershell
source-leap setup
source-leap doctor --probe
source-leap --latest --health --duration 10
```

Developers can select a LeapC library with `--library PATH` or `SOURCE_LEAP_LIBRARY`.
An explicit selection never silently falls back to another backend. Normal users
need neither option. See [runtime setup and caching](RUNTIME.md) for advanced setup.

[Documentation index](README.md)
