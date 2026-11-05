**Compatibility and performance - alpha 0.1.0a3, 5 November 2026**

The initial alpha required Python 3.12+. Alpha 0.1.0a2 lowers that requirement to
Python 3.10 and verifies the installed wheel on each minor version through 3.15.
Alpha 0.1.0a3 repeats the matrix with 62 tests, including local runtime preparation,
first-frame readiness, launcher reuse/ownership/failure handling, real Windows job
cleanup, and simulated service restoration after a delayed Windows stop error.
All checks below used Windows x64 and the existing Leap tracking service 3.2.1+45911.

| Python tested | Automated tests | Live camera frames | Recorded real-hand replay |
| --- | --- | --- | --- |
| 3.10.11 | 62 passed | 30 received | passed |
| 3.11.9 | 62 passed | 30 received | passed |
| 3.12.10 | 62 passed | 30 received | passed |
| 3.13.17 | 62 passed | 30 received | passed |
| 3.14.10 | 62 passed | 30 received | passed |
| 3.15.2 | 62 passed | 30 received | passed |

Each interpreter used a separate project-local venv. The wheel was installed into
site-packages, without relying on the source checkout or its editable install.
Dependency checks passed. The short live matrix checks contained empty-hand frames;
the real-hand replay check used an actual previously recorded five-finger skeleton.
Full live hand tracking was separately verified on 3.15.2. These are tests of the
listed patch versions, not every possible patch, operating system, or tracking runtime.
The managed launcher's existing-service mode separately received 30 live frames.
On Python 3.15.2 the private copied engine also delivered 1,047 frames over ten seconds,
including 50 full hand samples, with the system service stopped. All six versions
replayed that private recording exactly. See [minimal runtime evidence](MINIMAL_RUNTIME.md).
The private capture was mostly empty-hand frames, with recording enabled: its roughly
105 FPS is a functional observation, not an improvement claim or a CPU/latency comparison.
The detailed comparison measurements below are the earlier alpha-2 measurements.

Python 3.10 automatically installs `typing-extensions` for `Self` and `tomli` for
TOML parsing. On 3.11+, the standard library provides these facilities. UTC recording
timestamps use `timezone.utc` throughout. Internal deadlines use `perf_counter` to
keep timing precision consistent across the supported Windows interpreters. The
matrix caught a short-duration failure on 3.12 before this clock change; it passes
after the fix. Python 3.9 and earlier are not supported by this package.

**What changed to make modern Python work.** The camera driver and proprietary
tracking engine were not replaced. The original project imported a SWIG-generated
`Leap.py` and `LeapPython.pyd` linked specifically to `python38.dll`. The new working
path connects to the installed service's public protocol-v6 WebSocket endpoint at
`ws://127.0.0.1:6437/v6.json`, used by LeapJS. That interface is independent of the
CPython extension ABI, so a current Python client can read the existing service.

The package parses the messages into owned, immutable snapshots with documented
units, validates numeric data, and provides diagnostics, hand selection, configurable
coordinate mapping, recording/replay, and a CLI. There is also a separate native
LeapC backend, but it has not yet been validated for live frames with a compatible
newer runtime. The following performance results concern the working WebSocket path.

| Supplied data | Representation |
| --- | --- |
| Frame identity and acquisition time | frame ID and service-clock timestamp in microseconds |
| Hand identity and handedness | tracked ID plus left/right |
| Palm position and velocity | metres and metres/second |
| Palm orientation | quaternion derived from the service's normal/direction vectors |
| Palm normal, direction and width | unit vectors and metres |
| Grab and pinch | normalized strength, 0 to 1 |
| Fingers | identity/name, extended state, four bone segments per finger when supplied |
| Arm | elbow/wrist segment and width when supplied |
| Tracking visibility | time visible in microseconds |

Bone rotations and pinch distance are currently `None` in the WebSocket backend.
No robot-specific inverse kinematics, motor commands, activation states, adaptive
filtering, or complete teleoperation controller are supplied by this alpha.

**Observed rate.** The earlier standalone capture received 3,399 frames in 30 seconds,
about 113 frames/second. Simultaneous comparison runs observed about 101 to 109
frames/second. The service/camera supplies this varying rate; the library does not
force a fixed sensor rate. The human-readable CLI prints at most about 10 status
updates/second, while it continues consuming the full stream. Empty-hand frames
still count as camera frames. There is no claim that changing Python raises the
camera rate or improves the tracking algorithm's accuracy.

**Comparison method.** `tools/benchmark_tracking.py` runs three read-only consumers
against the same live stream: the original Python 3.8.10 SDK reading palm data, that
SDK materializing comparable hand/skeleton fields into Python tuples, and the new
Python 3.15.2 package producing validated snapshots. The old code is a minimal SDK
reader, not the original robot-sending scripts. Per-frame printing, recording, robot
transport, and filtering are disabled in all workers.

Windows QueryPerformanceCounter provides a shared clock across the processes.
Delivery comparisons match frame ID and acquisition timestamp, then compare the
time when each client's Python data is ready. This measures relative client delivery,
not absolute camera-to-robot or motion-to-action latency. Native tuples and validated
package objects have different construction/validation work, so the readers are
representative workloads rather than instruction-for-instruction equivalents.

**Initial full-hand run, before optimization.** Over 20 seconds a hand was visible
throughout. Both original readers received 2,176 frames; the new package received
2,175. All received frames contained hands.

| Reader | Frames/second | Process CPU, percent of one core |
| --- | --- | --- |
| Original Python 3.8, palm only | 108.80 | 2.50% |
| Original Python 3.8, hand/skeleton readout | 108.80 | 3.67% |
| New Python 3.15 package, before optimization | 108.75 | 10.86% |

For 2,175 matched hand frames, new data became ready 1.383 ms later than the old
skeleton reader at the median, and 2.113 ms later at the 95th percentile. The frame
rate was maintained, but this version was clearly more expensive in CPU and delivery
time. It would have been incorrect to describe it as faster.

**Measured optimization.** Profiling one captured 5,841-byte hand message found a
redundant Python-level UTF-8 validation pass costing approximately 572 microseconds
per message. Python's strict UTF-8 decoding of the same message took approximately
0.5 microseconds. The library already performs that strict decoding before returning
text, and JSON/numeric validation follows it.

The backend now uses `skip_utf8_validation=True` to remove the redundant pass; strict
UTF-8 decoding and application-data validation remain. These microbenchmarks are
illustrative costs on this machine, not portable performance guarantees.

**Follow-up after optimization.** This 20-second run had only 111 hand frames;
most other frames were empty. It therefore cannot be used as a full-hand CPU
comparison against the initial run.

| Reader | Frames/second | Process CPU, percent of one core, mixed run |
| --- | --- | --- |
| Original Python 3.8, palm only | 107.65 | 1.80% |
| Original Python 3.8, hand/skeleton readout | 107.45 | 2.27% |
| New Python 3.15 package, optimized | 108.90 | 1.64% |

Across the 111 matched hand frames, the new package was ready 0.039 ms later than
the old skeleton reader at the median, and 1.376 ms later at the 95th percentile.
Against the palm-only reader, those differences were 0.178 ms and 1.480 ms. OS
scheduling stalls affected the run. The differing frame counts are not evidence of
increased camera FPS, and the lower mixed-run CPU figure does not establish lower
CPU for sustained full-hand input. A longer repeat with a continuously visible hand
is still needed before making a strong performance claim.

The demonstrated result is broad Python compatibility, preserved stream throughput,
and reduced avoidable client overhead. A universal latency/CPU improvement over the
native SDK has not been established. Tracking accuracy uses the same engine.

The benchmark's local summaries are under `.tools/benchmarks`; raw hand captures and
machine-specific data are excluded from distributions. The first full-hand run is
`1793887813464487700/summary.json`; the optimized mixed run is
`1793888002722575600/summary.json`.

For actual robot integration, the next performance work should include an explicit
latest-frame mode with bounded buffering, frame-age checks, and testing the native
LeapC backend on a compatible service. Current `Tracker.read()` consumes the next
queued frame. A slow consumer can build a backlog; meeting the sensor rate in these
read-only tests is not a real-time robot-control guarantee.
