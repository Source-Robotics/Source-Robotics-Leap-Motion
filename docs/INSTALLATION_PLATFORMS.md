# Installation and platforms

The package targets the **Original Leap Motion Controller**. Start with the
[two Windows setup paths](../README.md#install-and-run-on-windows): install the official
tracking software yourself, or run the package's guided runtime setup after pip.

```powershell
python -m pip install --upgrade source-robotics-leap-motion
source-leap setup
source-leap teleop
```

The current public package is **0.1.0b3**. It requires Python 3.10 or newer; CPython
3.10–3.15 is the tested software matrix. No compiler or Python 3.8 helper is required.
The browser lab sends targets to a simulator. Real controllers use an explicit adapter.

## Platform status

| Platform | Runtime setup | Evidence and limits |
| --- | --- | --- |
| Windows x64 | Reuse a compatible service, or obtain the pinned private 3.2.1 engine through `source-leap setup` | Original-controller tracking, complete hand skeletons, delivery/cache, shared clients, restart/crash cleanup, and simulated teleoperation tested. Clean-PC driver setup pending. |
| Linux x86_64 | Install the compatible vendor service and native LeapC library | Native loading and common software interfaces tested in CI; real controller hardware remains experimental. |
| macOS Intel/Apple Silicon | Install matching vendor tracking software and native LeapC library | Native loading and common software interfaces tested in CI; real controller hardware remains experimental. |

The Windows runtime archive is not a Linux/macOS installer. Software CI tests do not
establish camera/USB support. Use the vendor's [Original-controller downloads](https://www.ultraleap.com/downloads/leap-controller/)
for currently offered operating systems and tracking software. Newer vendor engines
have not received the same live validation as the existing 3.2.1 Windows service.

## What pip and setup each do

Pip installs the Python API, CLI, packaged browser assets, and Python dependencies.
`source-leap setup` checks the connected controller and probes for actual frames.
It can obtain the separate Windows runtime, and an accepted interactive prompt or
explicit `--install-driver` requests OS approval for a missing USB driver. A working
driver is not replaced. A normal wheel installation is not an interactive OS setup hook.

The managed engine omits the vendor control panel and visualizer. Its download is
about **244 MB**, with about **251 MB** extracted, including driver files and notices.
The download is hash-pinned, resumable, and cached; later launches reuse it.
Imports perform no downloads, startup, or device connections.

## Linux and macOS

Follow the vendor's platform instructions before opening live tracking:

- Linux: the documented vendor package path targets Ubuntu 22.04 amd64. The core
  service is `ultraleap-hand-tracking-service`; GUI/OpenXR packages are separate.
  See [official Linux setup](https://docs.ultraleap.com/linux/index.html).
- macOS: select the matching Intel or Apple Silicon installation from the
  [Original-controller page](https://www.ultraleap.com/downloads/leap-controller/),
  start its tracking service, and grant requested OS access.

Then install the Python package and run `source-leap doctor --probe`. The
native loader searches documented installation locations. Raspberry Pi/ARM Linux
and arbitrary Linux distributions are not validated targets.

## Validation and advanced setup

- [b3 acceptance](B3_VALIDATION.md): live Windows hand workflow, 20-minute camera soak,
  Python matrix, and hardware gaps.
- [Clean-PC checklist](CLEAN_MACHINE_CHECK.md): exact procedure for a PC without an
  existing Leap driver/service; this hardware check is still pending.
- [Runtime guide](RUNTIME.md): offline installation, cache/catalog overrides, and
  developer bundles.
- [b1 validation](BETA_VALIDATION.md): earlier private-engine lifecycle checks.

[Documentation index](README.md)
