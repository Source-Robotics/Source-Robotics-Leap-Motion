# Maintainer tools

Users install from PyPI and run `source-leap setup` or `source-leap teleop`.
These scripts support source development, release preparation, and explicit hardware
measurements. Run Python tools with the source venv. Local output belongs in ignored
`dist/`, `.tools/`, or a chosen recording directory.

## Release utilities

| Tool | Purpose |
| --- | --- |
| [build_runtime_release.py](build_runtime_release.py) | Build a native runtime archive and descriptor from an approved local bundle |
| [configure_release.py](configure_release.py) | Pin the runtime download URL, sizes, and hash in the package catalog |
| [check_release.py](check_release.py) | Check built wheel contents and public runtime size; `--offline` skips the network probe |
| [download_release_artifacts.py](download_release_artifacts.py) | Fetch existing GitHub wheel/sdist and verify GitHub digests for PyPI publication |

See [releasing](../docs/RELEASING.md) before changing the runtime catalog or publishing.
Package releases can reuse the existing runtime; do not regenerate it for a docs change.

## Tracking and lifecycle measurements

| Tool | Requirements and effect |
| --- | --- |
| [benchmark_latest.py](benchmark_latest.py) | Compare sequential/latest consumers; supports `--demo` without hardware |
| [benchmark_tracking.py](benchmark_tracking.py) | Windows comparison against the old SDK; needs a separate Python 3.8 interpreter and historical bindings, which are not shipped in this repository |
| [probe_private_runtime.py](probe_private_runtime.py) | Receive/record frames from an explicitly prepared Windows runtime |
| [probe_runtime_lifecycle.py](probe_runtime_lifecycle.py) | Exercise private-engine sharing, restart, and crashed-client cleanup; requires an idle camera and the installed service already stopped |
| [Test-PrivateRuntime.ps1](Test-PrivateRuntime.ps1) | Coordinate a bounded private-runtime test and verify service restoration |
| [Pause-LeapForProbe.ps1](Pause-LeapForProbe.ps1) | Elevated helper that temporarily pauses/restores the installed Leap service for that explicit test |

The Python benchmark and probe scripts do not send robot commands. The PowerShell
test helper changes the installed service's running state temporarily and requests
Windows approval; it is not part of ordinary package setup. Keep hardware measurements
separate from software CI and identify the camera/service/Python versions in reports.

See [runtime setup](../docs/RUNTIME.md), [b3 acceptance](../docs/B3_VALIDATION.md), and
[the earlier runtime investigation](../docs/MINIMAL_RUNTIME.md).
