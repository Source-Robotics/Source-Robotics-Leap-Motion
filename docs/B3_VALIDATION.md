**b3 acceptance evidence — 6 November 2026**

The Original Leap Motion Controller was tested on the development Windows x64 PC,
using CPython 3.15.2 and its existing legacy 3.2.1 service. Control output went to
the simulated Cartesian arm. No physical robot was commanded or driver replaced.

**Guided live-hand run.** A 34.3-second run processed
2,777 frames, including 2,369 complete hand
samples (five fingers, four bones per finger), and generated 979
simulated targets. Calibration, clutch hold, re-anchoring without a command on the
re-anchor frame, removal of a visible hand, latched hold after its return, explicit
rearming with a new session, disarming, and adapter/tracker shutdown passed.

Preliminary runs also held output when a hand briefly disappeared. The successful
run used a stable-hand warmup and a shorter guided cycle to complete each transition.
The test harness changed; the product's conservative loss/rearm policy did not.

The Python control client used 2.87% of one
core averaged over this mixed hand-present/hand-absent run. Local receipt age at
sampling was 0.085 ms median and
0.205 ms p95. These ages start when Python receives
a distinct frame; they are not exposure-to-command or camera latency measurements.
CPU figures exclude the vendor service and are not a matched comparison with the old SDK.

**Twenty-minute camera soak.** 1200.0 seconds processed
115,180 frames, including 7,179 complete hand
samples. The camera continued streaming with the hand absent for much of the run.
There were 0 read timeouts. Average delivery was
96.0 FPS; Python-client CPU averaged
2.51% of one core.

Final working set was 31.66 MiB and lifetime peak
working set was 31.66 MiB. These are Windows
process counters for this Python client, collected with
[GetProcessMemoryInfo](https://learn.microsoft.com/en-us/windows/win32/api/psapi/nf-psapi-getprocessmemoryinfo),
not the vendor engine or total system footprint. History in the runner was bounded.
The tracker closed and left 0 reader threads.

**Package checks.** The installed b3 code passed 180 tests on each Windows CPython
3.10–3.15 environment, plus all 18 Windows/Linux/macOS CI matrix jobs and the build.
The existing real-hand recording passed simulated control checks on each interpreter.
A fresh Python 3.10 candidate installation passed the headless control demo, packaged
HTML/JavaScript/CSS serving, dependency checks, and thread-free import. Artifact
inspection found no native binaries or personal recordings. Release documentation
updates leave the tested package code, assets, and pinned runtime unchanged.

**Remaining hardware evidence.** The owner has no spare clean Windows PC available
and chose to continue with the simulator. Clean-PC USB driver setup, actual robot
adapter/controller behavior, and Linux/macOS USB operation remain unverified.
The [clean-machine checklist](CLEAN_MACHINE_CHECK.md) records the test procedure.
Fresh venv and hosted software CI results are not a substitute for those device tests.

Raw local evidence is retained in `.tools/live-b3-acceptance.json`, its earlier-attempt
reports, `.tools/soak-b3-result.json`, `.tools/b3-candidate-install.json`,
`.tools/b3-artifact-audit.json`, and `.tools/compatibility-results-0.1.0b3.json`.
