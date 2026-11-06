# Contributing

The installable package lives in `src/source_robotics_leap_motion/`. User installation
starts in the [README](README.md); the [documentation index](docs/README.md) covers
usage, architecture, and validation. Work on a branch and keep changes focused.
Git and editor settings use UTF-8 text with LF line endings on every platform.

## Set up a source checkout

Use 64-bit CPython 3.10 or newer. From the repository root on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\source-leap.exe teleop --demo
```

On Linux/macOS, the equivalent interpreter is `.venv/bin/python` and the console
command is `.venv/bin/source-leap`. The demo and software checks need no controller
or vendor tracking installation. Live hardware on those systems remains experimental.
Calling the venv executables directly avoids activation and PowerShell policy changes.

## Check a change

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests examples
.\.venv\Scripts\python.exe -m ruff format --check src tests examples
.\.venv\Scripts\source-leap.exe teleop --demo --headless --auto-arm --frames 3
.\.venv\Scripts\python.exe -m build
```

CI additionally checks the release/runtime tools named in
[ci.yml](.github/workflows/ci.yml), builds the wheel/sdist, checks metadata, and runs
the Python 3.10–3.15 matrix on Windows, Linux, and macOS. Run focused behavioral
tests for code changes and a build/content check for packaging changes. Documentation
changes need working links and commands; a full hardware run is unnecessary when
runtime behavior is unchanged.

## Keep the package boundaries clear

- Put device/protocol conversion in `backends/`; expose owned Python frames in SI units.
- Keep coordinate mapping and the control state machine independent of a robot SDK.
- Wrap controller-specific calls through `adapters/`, with capabilities, feedback,
  hold, and close behavior. Joint-only controllers provide their own kinematics.
- Imports must not open devices, start engines/threads, download files, or move a robot.
- Hardware tests and native assets are explicit. Keep local recordings, credentials,
  downloaded runtimes, `.venv/`, `.tools/`, and build outputs out of Git.

See [architecture](docs/ARCHITECTURE.md) and [teleoperation](docs/TELEOPERATION.md)
for the existing contracts. Describe validation in a PR and state when real hardware
was or was not involved. Historical demo material is under [docs/history](docs/history/README.md).

## Report a problem

Include the package/Python version, operating system/CPU architecture, controller model,
installation path (official vendor service or managed runtime), and steps to reproduce.
For setup problems, include the relevant output of:

```powershell
source-leap --version
source-leap setup --json
source-leap doctor --probe --json
```

Review diagnostic output before posting paths or device details publicly. A useful
controller-integration request names the SDK/protocol, Cartesian versus joint input,
units, feedback, and available hold/expiry behavior.

Release maintainers should follow [the release guide](docs/RELEASING.md).
