# b4 validation — 6 November 2026

This report covers independent gripper filtering/cadence and the optional simulated
receiver in 0.1.0b4. The Leap tracking engine, runtime pin, and base dependencies are
unchanged. The implementation uses the package's existing geometry/contracts and
standard library; UltraGrasp supplied design ideas, with no external source bundled.

## Installed Windows wheel

The candidate wheel passed **233 tests on each** of CPython 3.10.11, 3.11.9,
3.12.10, 3.13.17, 3.14.10, and 3.15.2 in isolated Windows x64 venvs. Imports resolved
from site-packages, the import/metadata versions matched, and pip check passed.

Each environment also received 30 live sequential frames and 30 latest-mode frames,
round-tripped the 1,047-frame recording containing 50 complete hand samples, ran
30 interpolated demo frames, and executed the deterministic expiry example.
No hands were visible during the new live probes; full-skeleton input came from
the previously recorded real hand. These checks do not establish a new camera FPS,
tracking-accuracy, or end-to-end latency improvement.

## Combined recorded-hand run

The real 1,047-frame recording drove the control engine and deterministic receiver
together using its recorded intervals. The run generated **18 pose commands
and 9 gripper updates**, with a 0.12-second independent gripper time constant
and 30 Hz gripper cap. Receiver Cartesian workspace, linear/angular speed, and
normalized gripper speed checks passed. Clutch held output, explicit resume used a
fresh re-anchor and sender sequence watermark, and tracking loss stayed latched.
There were **zero commands after loss and zero receiver rejections** in this valid run.

## One-minute simulated receiver soak

A 60.0-second synthetic-hand run processed 3,457 control steps and
3,440 simulated targets. Five deliberate 0.22-second sender pauses caused
receiver-owned expiry before the sender called it again. Tracking loss emitted no
additional command; explicit recalibration created six distinct sessions in total.
The receiver worker and tracking reader both closed cleanly.

Python CPU averaged 2.55% of one core for this synthetic, headless
process, including its tracking and receiver workers. This excludes the vendor engine
and browser and is not a hardware or prior-version performance comparison.

## Receiver and lifecycle regressions

Behavioral tests verify interpolation continuity under replacement/jitter, per-channel
speed/workspace enforcement, local timeout caps, expiry at the correct instant after
a delayed tick, and expiry while the sender is not calling the simulated adapter.
Duplicates, wrong-session commands, invalid fields, and out-of-order packets do not
refresh deadlines. Pose-only packets do not extend prior gripper/rotation deadlines.

Clutch resume supplies the sender's last produced sequence, so even previously unseen
packets delayed from before clutching are rejected. Expired streams require a new
session; invalid receiver clocks latch faults. Construction starts no worker, and
close joins it even after an injected worker/close failure. Existing immediate
simulation and omitted gripper settings retain their previous behavior.

## Platform CI and packaging

Code commit: `693c666192ba9846ccbc09ebc8e913f9670a59d1`.
Platform CI results are available at the linked run; completion is still pending.
[CI run](https://github.com/Source-Robotics/Source-Robotics-Leap-Motion/actions/runs/42253682504).

Hosted CI covers Python 3.10–3.15, software behavior, installed CLI demos, and package
builds. Local checks include Ruff, JavaScript syntax, wheel-from-sdist builds, strict
Twine metadata, source-archive contents, documentation links, and candidate installs.
Versioned runtime and vendor notice contents are retained; no native code, numerical
toolbox, robot SDK, recording, or private runtime is added to the Python wheel.

## Scope

Output was simulated. No physical robot command, service-state change, or USB driver
installation occurred. The receiver worker is a software scheduling demonstration,
not a real-time guarantee or physical robot watchdog. An actual integration must
enforce expiry/hold where it can still act after the sender or network disappears.

The earlier live calibration/clutch/hand-loss acceptance and 20-minute camera soak
remain documented in [b3 validation](B3_VALIDATION.md). Clean-Windows driver-only
installation, Linux/macOS controller hardware, and actual robot integration remain
pending.

[Receiver guide](RECEIVER.md) · [Documentation index](README.md)
