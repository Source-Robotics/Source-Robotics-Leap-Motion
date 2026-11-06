# Runtime setup and caching

For ordinary installation, use [one of the two Windows setup paths](../README.md#install-and-run-on-windows).
This guide covers runtime ownership, advanced setup, and developer bundles.

## Automatic selection

`Tracker()` and `source-leap` reuse an installed compatible service or select the
cached private Windows runtime. If neither is available, the release catalog supplies
a pinned Windows download. SHA-256 and file sizes are checked, interrupted transfers
resume, and installation is atomic. The compressed download is removed after
installation to retain one extracted copy.

The released bundle is about **244 MB compressed and 251 MB extracted**, including
driver files and notices. The Python wheel does not contain vendor executables, DLLs,
or models. Imports perform no downloads, device access, or background startup.

Auto mode supports installed LeapC and the local protocol-v6 WebSocket service.
The live Windows evidence uses service `3.2.1+45911`; newer native engines and
Linux/macOS do not have the same hardware validation. Existing working legacy
services can be reused without upgrading them.

## Device and driver setup

```powershell
source-leap setup
source-leap doctor --probe
```

Setup reports device status and probes actual frames. An unplugged device differs
from Windows problem code 28 (missing driver). An accepted interactive driver prompt
or `source-leap setup --install-driver` requests Windows administrator approval.
A working driver is not replaced. `--open-downloads` opens the official platform page.
`--download-only` prepares the runtime without opening the camera.

Clean-PC driver installation still needs a separate hardware check; see
[the checklist](CLEAN_MACHINE_CHECK.md). Linux/macOS require their own compatible
vendor service and OS device-access setup. See [platforms](INSTALLATION_PLATFORMS.md).

## Offline and deployment overrides

Download the pinned runtime archive in advance for offline Windows setup:

```powershell
source-leap setup --archive source-leap-runtime-windows-x86_64-3.2.1.zip
```

`SOURCE_LEAP_CACHE` selects a development/test cache. `--catalog PATH` selects an
explicit setup/deployment catalog. Normal users need no environment variables.
`--library PATH` or `SOURCE_LEAP_LIBRARY` selects a developer LeapC library without
silently falling back to another backend.

## Prepare a developer bundle

From a source checkout, a developer can copy the allowlisted engine files from an
existing local installation. `--dependencies` points to the directory containing
the required VC++ support DLLs; supply the actual local directory.

```powershell
source-leap runtime prepare "C:\Program Files (x86)\Leap Motion\Core Services" --destination .tools\private-runtime-321 --dependencies .
source-leap runtime inspect .tools\private-runtime-321
source-leap monitor --runtime-dir .tools\private-runtime-321
```

Preparation records checksums and excludes the vendor control panel/visualizer.
Applications acquire leases from a hidden coordinator that starts the private engine
and waits for an actual frame. Closing one client keeps tracking alive for others.
The engine exits after the final client leaves, including clients that crash.
Configuration and logs live outside the engine directory. The package does not stop
or install system services. `Tracker(runtime_dir="...")` selects a developer bundle
explicitly.

[Maintainer tools](../tools/README.md) explain the optional service-pause and lifecycle
checks. Those development checks are separate from normal installation. Earlier
measurements are in [the runtime investigation](MINIMAL_RUNTIME.md) and
[b1 validation](BETA_VALIDATION.md).
