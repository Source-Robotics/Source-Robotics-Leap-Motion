**Source Robotics Leap Motion**

A Python package for the **Original Leap Motion Controller**, with owned hand data,
recording/replay, and configurable coordinate mapping for custom robot integrations.
It runs on current Python without `LeapPython.pyd` or a Python 3.8 process.

Beta **0.1.0b2** is published on [PyPI](https://pypi.org/project/source-robotics-leap-motion/).
Install it, then start tracking:

```powershell
python -m pip install source-robotics-leap-motion
source-leap
```

The Windows engine downloads automatically when needed. First-use driver setup may
require Windows approval. See [release status and validation](docs/BETA_VALIDATION.md)
and [publication steps](docs/RELEASING.md). Linux/macOS currently use an installed
vendor tracking service and remain experimental for hardware use.

This checkout contains **0.1.0b3 development**, adding configurable Cartesian
teleoperation, callback integration, and a browser lab with simulated output. These
teleoperation features are available from source. Latest-frame acquisition and
tracking health are included in the published **0.1.0b2** package. See
[the teleoperation guide](docs/TELEOPERATION.md) and [latest-frame guide](docs/LATEST_FRAMES.md).

Try the simulated robot target with a synthetic hand, or with your Leap controller:

```powershell
.\.venv\Scripts\source-leap.exe teleop --demo
.\.venv\Scripts\source-leap.exe teleop
```

The local browser viewer starts disarmed. Arm to calibrate, clutch to reposition
your hand, and disarm to hold output. Both commands use a simulated Cartesian arm.
The callback API accepts your own controller; joint-only arms supply their kinematics
in the adapter. Configure workspace, speed limits, axes, gains, smoothing, rotation,
and gripper mapping in [teleoperation.toml](examples/teleoperation.toml).

**Try it in this project's virtual environment.** Python 3.15.2 and the package are
already installed in `.venv`. No activation is necessary:

```powershell
.\.venv\Scripts\source-leap.exe --demo
.\.venv\Scripts\source-leap.exe setup
.\.venv\Scripts\source-leap.exe doctor --probe
.\.venv\Scripts\source-leap.exe
```

The first command shows synthetic hand motion. The last uses a connected controller.
Stop with Ctrl+C. Add `--frames 60` or `--duration 5` for a bounded run.
`source-leap.cmd --demo` is a convenience wrapper for this checkout.

To install the source in another existing environment:

```powershell
python -m pip install .
source-leap --demo
```

Python **3.10 or newer** is required. The published b2 wheel was installed and tested on
**CPython 3.10.11, 3.11.9, 3.12.10, 3.13.17, 3.14.10, and 3.15.2, Windows x64**.
Each version passed all 107 tests, received live camera frames, and replayed a recorded
real hand. Python 3.10 additionally uses small `tomli` and `typing-extensions`
backports, installed automatically by pip. All versions use `websocket-client`.
Python 3.9 and earlier are not supported by the new package.

The [compatibility and performance report](docs/COMPATIBILITY_PERFORMANCE.md) explains
the test matrix, measured stream rate, comparison with the original Python 3.8 SDK,
and remaining limits. The tracking engine and driver are unchanged; no improvement
in tracking accuracy or camera frame rate is claimed.

**Automatic runtime selection.** `Tracker()` and `source-leap` reuse an installed
compatible service or find the cached private runtime automatically. If neither is
available, the release catalog supplies a pinned Windows download. Its SHA-256 and
file sizes are checked, interrupted transfers resume, and installation is atomic.
The compressed download is removed after installation to keep one extracted copy.
Imports perform no downloads, device access, or background startup.

The service path supports LeapC and the local protocol-v6 WebSocket endpoint.
On this PC, the fallback was verified with service `3.2.1+45911` on
`127.0.0.1:6437` and the actual Original Leap Motion Controller. A 30-second check
captured 3,399 frames, including 53 frames containing a left hand with all five
fingers and four bones per finger. Recording and replay also passed. See
[the hardware validation notes](docs/HARDWARE_VALIDATION.md).

An existing working legacy service can therefore be used without upgrading it.
The native LeapC loader supports Windows x64, Linux x64, and macOS Intel/Apple
Silicon. Linux/macOS hardware integration remains experimental and needs a compatible
vendor service. Windows private-engine operation has been hardware-tested. No vendor
DLLs or model data are included in the Python wheel; the Windows runtime is a separate
GitHub release asset. Clean-PC driver setup still needs a real hardware test.

**First-use setup.** `source-leap setup` reports device status and probes actual frames.
An unplugged device is distinguished from Windows problem code 28 (missing driver).
Only an explicit `--install-driver` action or an accepted interactive prompt requests
Windows approval. A working driver is not replaced. `--open-downloads` opens the
official platform setup page. Linux instructions point to the vendor's core service
package; macOS instructions select the appropriate vendor installation.

An offline Windows installation is also available:

```powershell
.\.venv\Scripts\source-leap.exe setup --archive dist\runtime\source-leap-runtime-windows-x86_64-3.2.1.zip
```

`SOURCE_LEAP_CACHE` selects a development/test cache. Normal users need no environment
variables. `--catalog PATH` is a setup/deployment override for a release catalog.

**Private Windows runtime.** Developers can prepare a local engine copy without the
control panel or visualizer:

```powershell
.\.venv\Scripts\source-leap.exe runtime prepare "C:\Program Files (x86)\Leap Motion\Core Services" --destination .tools\private-runtime-321 --dependencies .
.\.venv\Scripts\source-leap.exe runtime inspect .tools\private-runtime-321
.\.venv\Scripts\source-leap.exe monitor --runtime-dir .tools\private-runtime-321
```

Preparation copies local files and records checksums. Applications acquire leases on
a hidden coordinator that starts the engine and waits for an actual camera frame.
Closing one application keeps the engine alive for other clients. The engine exits
after the last client leaves, including crashed clients. Configuration and logs live
outside the engine directory. The package never stops or installs system services.
`Tracker(runtime_dir="...")` selects a developer bundle explicitly.

The base engine contains seven files, about **248 MB** before compression. The release
archive adds driver files and notices: **251 MB extracted, 244 MB compressed**.
The private engine delivered 1,047 frames in ten
seconds, about 105 FPS, including 50 full hand skeletons. It ran as the normal user
while the installed service was stopped. First-frame startup took about 2.6 seconds.
The project owner confirmed redistribution permission on 5 November 2026. The
installed beta wheel also passed two-client sharing, repeated startup, crash cleanup,
and a live-frame check of the restored installed service. Clean-PC USB setup and
other-platform hardware tests remain pending.
See [the prototype, evidence, and bounded test command](docs/MINIMAL_RUNTIME.md).
The proposed first-use flow and Windows/Linux/macOS targets are documented in
[installation and platforms](docs/INSTALLATION_PLATFORMS.md).

**Read hand data.** The same API accepts live, synthetic, and replay sources:

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

**Latest frames and health (0.1.0b2).** A slow application can request
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
inside a service or transport. See [semantics and validation](docs/LATEST_FRAMES.md).

```powershell
.\.venv\Scripts\source-leap.exe --latest --health --duration 10
.\.venv\Scripts\source-leap.exe --demo --latest --health --frames 60 --json
```

Health JSON goes to stderr; frame JSON on stdout and the recording schema are unchanged.

**Record and replay.** Existing recordings are protected by default:

```powershell
.\.venv\Scripts\source-leap.exe record recordings\session.jsonl --frames 300
.\.venv\Scripts\source-leap.exe replay recordings\session.jsonl --realtime
.\.venv\Scripts\source-leap.exe record recordings\demo.jsonl --demo --frames 60
.\.venv\Scripts\source-leap.exe replay recordings\demo.jsonl --json
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

**Customize coordinate mapping.** The package provides a pure mapping function, with
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
Run `python examples/custom_mapping.py` for a complete synthetic example that only
prints targets.

This alpha supplies tracking and mapping primitives. Robot adapters, activation/clutch
states, motion limits, adaptive filtering, and continuous robot control are the next
milestone; a production `Teleoperator` is **not implemented**. There is no automatic
connection to an arm, no motor-driver dependency, and no implicit movement command.

**Diagnostics.** `doctor` inspects fixed runtime locations without loading native
code. `doctor --probe` also opens tracking and waits for a frame. Exit code 0 indicates
the requested check passed, 2 indicates a configuration/tracking error, and Ctrl+C
returns 130. A WebSocket connection can succeed while the camera is unplugged, paused,
or otherwise not streaming; a successful greeting alone is not a live-frame test.

Developers can explicitly select a LeapC library with `--library PATH` or the
`SOURCE_LEAP_LIBRARY` environment variable. An explicit selection never silently
falls back to another backend. Normal users should not need either option.

**Development and validation.**

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests examples
.\.venv\Scripts\python.exe -m ruff format --check src tests examples
.\.venv\Scripts\python.exe -m build --wheel
```

The original scripts and binaries remain historical references. The original README
is preserved in [docs/LEGACY_README.md](docs/LEGACY_README.md). Current scope and design
are in [PACKAGE_DESIGN.md](PACKAGE_DESIGN.md); native-interface verification is described
in [docs/NATIVE_ABI.md](docs/NATIVE_ABI.md).
