# Documentation

Start with [installation and the two Windows setup paths](../README.md#install-and-run-on-windows).
The current public package is **0.1.0b3**. Windows tracking and simulated output have
live hardware evidence; clean-PC driver setup and Linux/macOS hardware remain pending.

## Using the package

| Guide | What it covers |
| --- | --- |
| [Python API and CLI](USAGE.md) | Hand data, units, recording/replay, mapping, and diagnostics |
| [Teleoperation and adapters](TELEOPERATION.md) | Browser lab, calibration, clutch, limits, TOML, and controller callbacks |
| [Latest frames and health](LATEST_FRAMES.md) | Slow consumers, freshness, skipped frames, and health semantics |
| [Installation and platforms](INSTALLATION_PLATFORMS.md) | Supported setup paths and platform limitations |
| [Runtime setup](RUNTIME.md) | Automatic download/cache, driver prompts, offline setup, and private engines |
| [Examples](../examples/README.md) | Runnable examples and configuration files |

## Developing and releasing

| Guide | What it covers |
| --- | --- |
| [Contributing](../CONTRIBUTING.md) | Source venv, checks, package boundaries, and bug reports |
| [Architecture](ARCHITECTURE.md) | Tracking, control, adapters, and runtime ownership |
| [Maintainer tools](../tools/README.md) | Release scripts and hardware measurement utilities |
| [Releasing](RELEASING.md) | Build validation, immutable artifacts, and Trusted Publishing |
| [Native ABI verification](NATIVE_ABI.md) | Header provenance and checked native layouts |
| [Vendor notice](VENDOR_NOTICE.txt) | Notices accompanying the separately delivered runtime |

## Validation evidence

Measurements belong to the version and hardware named in each report. Passing hosted
CI does not establish USB/controller support on an untested operating system.

| Report | Scope |
| --- | --- |
| [b3 acceptance](B3_VALIDATION.md) | Current live-hand behavior, 20-minute soak, Python matrix, and remaining checks |
| [Clean Windows checklist](CLEAN_MACHINE_CHECK.md) | Procedure for a PC without an existing Leap installation; still pending |
| [b1 runtime validation](BETA_VALIDATION.md) | Earlier delivery, caching, shared leases, restart, and crash cleanup |
| [Compatibility and performance](COMPATIBILITY_PERFORMANCE.md) | Earlier Python-version checks and old-SDK comparison measurements |
| [Initial hardware validation](HARDWARE_VALIDATION.md) | Original service, first complete skeletons, and recording/replay |
| [Private-runtime investigation](MINIMAL_RUNTIME.md) | Earlier reduced Windows bundle investigation and measurements |

## History

The [history index](history/README.md) separates earlier design proposals and original
demo documentation from current instructions. Historical roadmaps are not the current
API reference.
