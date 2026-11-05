**Local runtime prototype - alpha 0.1.0a3, 5 November 2026**

The target is one Python-package installation that manages the essential tracking
runtime, without a separate control panel, visualizer, demos, or OpenXR integration.
Alpha 3 implements local preparation and process management. It does not yet supply
vendor binaries, download an engine, install a driver, or deliver that clean-PC promise.

**Implemented.** `runtime prepare` copies an explicit allowlist from a local legacy
installation. It records SHA-256 checksums, adopts matching files on repeat runs,
and refuses to overwrite different runtime files. `runtime inspect` verifies the
manifest, required names, file sizes, and checksums. These are corruption checks;
they do not establish vendor authenticity or distribution rights.

`ManagedLegacyBackend` checks local port 6437 and reuses an existing protocol-v6
service when allowed. Otherwise it validates the bundle, writes its own configuration,
and starts `LeapSvc64.exe --run --config=...` with no console window. Camera images
and remote WebSocket access are disabled in that configuration. The package connects
to the engine through the same legacy tracking backend already verified on hardware.
Readiness requires the first actual camera frame, not merely a WebSocket greeting;
the launcher caches that frame for the caller. This covers the model/camera startup
interval, which was about 2.6 seconds on this PC.

The launcher owns only its child process. Startup failures and normal context exit
clean up that process, connection, log, and Windows job handle. A Windows job configured
with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` also ends assigned children when its final
handle closes. The launcher never stops, installs, or removes system services.
[Windows process assignment](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject),
[Windows job limits](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information)

**Candidate files from this PC's service 3.2.1.** The project-local copy is
`.tools/private-runtime-321`:

| Component | Bytes |
| --- | ---: |
| `LeapSvc64.exe` | 9,935,288 |
| `Tracking.ldat` | 236,511,170 |
| Three firmware `.ldat` files | 193,601 |
| `msvcp120.dll` and `msvcr120.dll` | 1,623,360 |
| Total runtime payload | 248,263,419 |

That is about 248 MB decimal, or 237 MiB, uncompressed. No Qt/control-panel files
were copied. Two alternate models, totaling another 116,978,286 bytes, are omitted
by default and can be included with `--extra-models`. The seven-file set produced real
hand tracking; it is a tested candidate, not proof of the smallest possible file set.
The manifest, configuration, and logs add a small amount beyond the payload above.
A streaming ZIP-deflate measurement at level 6 produced 241,380,986 bytes for these
files plus the manifest. No archive was saved or redistributed. The model dominates
both disk and compressed size; excluding GUI components does not make it a tiny runtime.

**Evidence and limits.**

- The copied executable runs `--help` with these local support DLLs. Its actual help
  lists `--run` for interactive service operation and `--config` for a configuration path.
- The managed launcher's reuse mode received 30 live camera frames. Exclusive mode
  refused the occupied port without starting another engine or modifying the service.
- All 62 tests passed from the installed wheel in project-local venvs on CPython
  3.10.11, 3.11.9, 3.12.10, 3.13.17, 3.14.10, and 3.15.2. Tests include bundle validation,
  readiness, reuse, startup failures, termination fallback, a real child killed by job
  closure, and service restoration after a simulated delayed Windows stop error.
- After Windows approval, the private engine captured 526 empty-hand frames in five
  seconds at 104.8 FPS. A second capture produced 1,047 frames over ten seconds at
  104.6 FPS, including 50 complete left-hand samples. Each sample had five fingers,
  four bones per finger, and arm data. The engine ran as the ordinary user while the
  installed service was stopped. No control panel or visualizer ran for capture.
- The hand capture started in 2.55 seconds, its child exited on cleanup, and the
  system `config.json` hash stayed unchanged. All 1,047 snapshots replayed exactly;
  timestamps were nondecreasing and palm orientations had unit length. The capture
  was mostly empty-hand frames, so it is not a sustained-hand performance benchmark.
- One restoration reached service status `Running` but did not resume camera frames.
  A later service restart restored verified live frames. During recovery, Windows
  reported a stop error but completed the stop afterward. The helper has been corrected
  to restore the original running state even after that error, uses non-waiting stop
  requests and bounded status waits, and now checks actual frames after restoration.
  Repeated, reliable camera handoff remains a production-readiness check.
- Existing USB drivers remain installed. Supplied INF files associate the camera with
  WinUSB, but that does not establish what happens on a clean PC.

**Try the prepared bundle.** These commands run in the project's existing venv:

```powershell
.\.venv\Scripts\source-leap.exe runtime inspect .tools\private-runtime-321
.\.venv\Scripts\source-leap.exe runtime probe .tools\private-runtime-321 --frames 30
```

The probe reports `"mode": "existing"` if the installed service is active. Read that
mode before attributing success to the copied engine.

For a bounded exclusive test on this PC, run this from a **normal** PowerShell terminal:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\Test-PrivateRuntime.ps1
```

Approve the Windows prompt. Only `Pause-LeapForProbe.ps1` runs elevated. It temporarily
stops the existing service, signals readiness, and restores the original running
state in `finally`, with a separate 60-second pause watchdog. The private engine runs
under the ordinary parent account. The Python probe captures for five seconds and
reports frame rate, hand frames, child exit, and whether the existing system config
hash changed. Results go under the local runtime's `state/probe-...` directory.
This helper is a development test, not the proposed end-user installation flow.
`-CaptureSeconds 10` extends capture to ten seconds. A local recording is saved with
each test. If restoration reports no frames, the check fails even if service status
is `Running`; that status alone is insufficient evidence of working tracking.

The verified hand capture is under
`.tools/private-runtime-321/state/probe-10d13e0141ef4d479f4382e2fed2f3c0`, with
`summary.json`, `tracking.jsonl`, and `validated.json`. All are excluded from packages.

To test without that helper when the existing service is already stopped:

```powershell
.\.venv\Scripts\python.exe tools\probe_private_runtime.py .tools\private-runtime-321
```

**What remains before shipping.** Clean-PC USB setup, repeatable camera lifecycle,
long sessions, and operation without any other vendor installation must be verified.
The project owner confirmed on 5 November 2026 that redistribution is permitted.
That confirmation is the project's permission basis; permission is no longer treated
as a pending request. Runtime delivery and its accompanying notices still need to be
assembled. No vendor engine, DLL, or model is currently included in our wheel or
source distribution, and the package is not on PyPI. See
[the installation and platform plan](INSTALLATION_PLATFORMS.md).

The vendor's Linux packages separate the core service from GUI components. That is
useful deployment precedent, but it does not validate this Windows portable prototype.
[Vendor Linux package breakdown](https://docs.ultraleap.com/linux/index.html)
