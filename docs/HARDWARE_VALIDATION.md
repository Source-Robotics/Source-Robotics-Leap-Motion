> Versioned historical evidence: this report describes the release or prototype
> named below. For current status, see [b3 acceptance](B3_VALIDATION.md) and the
> [documentation index](README.md).

**Original Leap Motion Controller - live validation, 5 November 2026**

The first alpha was tested against the user's connected **Original Leap Motion
Controller** in this project's Python virtual environment.

| Component | Observed value |
| --- | --- |
| Package | source-robotics-leap-motion 0.1.0a1 |
| Interpreter | CPython 3.15.2, x64 |
| Operating system | Windows 11 |
| Installed tracking service | 3.2.1+45911 |
| Selected backend | legacy-websocket |
| Local endpoint | ws://127.0.0.1:6437/v6.json |
| Capture duration | 30 seconds |
| Frames captured | 3,399 |
| Frames containing a hand | 53 |
| Observed handedness | left |
| Finger skeleton | five fingers, four bones per finger |
| Arm data | present |

The capture exercised real palm positions, derived palm orientation, finger and arm
joint positions, frame timestamps, and coordinate mapping. Quaternion unit length
was checked on every tracked-hand frame. Timestamps did not move backwards. All
frames, including valid empty-hand frames, were written to the versioned recording
format and read back successfully. The replayed count and exact first/last snapshots
matched the capture.

The temporary capture and machine-readable summary are under `.tools`, excluded
from both source and wheel distributions. They were not made into public test
fixtures. The local wheel installed in a separate clean venv also received a live
camera frame through `doctor --probe`.

This verifies that the current-Python package can obtain hand data from the original
controller using the existing legacy service, without a Python 3.8 helper or a service
upgrade. The capture is a functional check, not a latency benchmark or certification
of robot-control timing.

Since the initial capture, installed-wheel checks have passed on Python 3.10 through
3.15; see [the compatibility report](COMPATIBILITY_PERFORMANCE.md). Alpha 3 also ran
the copied engine privately, as the normal user with the installed service stopped.
That ten-second capture produced 1,047 frames, including 50 left-hand frames with
five fingers, four bones per finger, and arm data. Every recorded snapshot replayed
exactly, timestamps were nondecreasing, and palm orientations had unit length.

The private child exited and the system configuration hash stayed unchanged. One
restoration reported the Windows service as running without a camera stream. A
subsequent service restart restored actual live frames. The development helper now
checks live frames after restoration and handles a delayed stop error. See
[private-runtime evidence and limitations](MINIMAL_RUNTIME.md).

Outstanding checks include repeated camera handoff, two-hand operation on hardware,
disconnect/reconnect behavior, extended sessions, clean-PC USB setup, other platforms,
and native LeapC streaming with a compatible newer service. The current automated
suite has 62 passing tests. Robot control is not implemented by this alpha.
