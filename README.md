# Source Robotics Leap Motion

[![PyPI](https://img.shields.io/pypi/v/source-robotics-leap-motion?include_prereleases)](https://pypi.org/project/source-robotics-leap-motion/)
[![Tests](https://github.com/Source-Robotics/Source-Robotics-Leap-Motion/actions/workflows/ci.yml/badge.svg)](https://github.com/Source-Robotics/Source-Robotics-Leap-Motion/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/Source-Robotics/Source-Robotics-Leap-Motion/blob/main/LICENSE)

A Python package for the **Original Leap Motion Controller**. Read hand skeletons,
record and replay motion, and map hand movement to a simulator or your own robot
controller through configurable adapters.

**Status:** [Published Windows beta on PyPI](https://pypi.org/project/source-robotics-leap-motion/).
Windows tracking and the simulated robot workflow have passed live-controller tests.
Clean-PC driver installation and Linux/macOS controller hardware tests are still pending.

## Install and run on Windows

You need **64-bit Python 3.10–3.15**, Windows 10/11, and an **Original Leap Motion
Controller** connected by USB. Open PowerShell and choose **one** installation path.

### Option 1: Install the official Leap software yourself

1. Open [Ultraleap's Original Leap Motion Controller downloads](https://www.ultraleap.com/downloads/leap-controller/).
   For the hardware-tested Windows setup, choose **Orion 3.2.1** and run its installer.
   If you already have a compatible working Leap service, keep it.
2. Connect the controller and check that the vendor software can see your hand.
3. Install our Python package and open the viewer:

```powershell
python -m pip install --upgrade source-robotics-leap-motion
source-leap teleop
```

The vendor installer supplies the tracking service and USB driver. Our package
supplies the Python API and viewer; no separate Python SDK installation is needed.
The native backend also supports LeapC, but newer vendor engines have not received
the same live-hardware validation as 3.2.1.

### Option 2: Let our package set up the runtime

Connect the controller, then run:

```powershell
python -m pip install --upgrade source-robotics-leap-motion
source-leap setup
source-leap teleop
```

Setup reuses a compatible service if one is running. Otherwise it downloads and
caches our pinned Windows runtime, about **244 MB**, and checks for live camera
frames. If Windows reports a missing USB driver, answer **y** to the installation
prompt and approve Windows' administrator prompt. Wait for **Tracking: ready**
before opening the viewer. If setup fails, use Option 1 or see the
[clean-machine checklist](https://github.com/Source-Robotics/Source-Robotics-Leap-Motion/blob/main/docs/CLEAN_MACHINE_CHECK.md).

This path uses the tracking engine without installing the vendor control panel or
visualizer. The runtime and driver are obtained during setup, rather than inside
`pip install`. First setup needs internet access; subsequent launches reuse the cache.
Driver installation on a Windows PC with no previous Leap software still needs
independent hardware validation.

### Start using it

The browser viewer opens with a **simulated robot target** and starts disarmed. Put
your **right hand** above the controller and click **Arm & calibrate**. Use **Clutch**
to reposition your hand and **Disarm** to hold output. Hand selection and the robot
controller adapter are configurable.

After installation, the daily command is:

```powershell
source-leap teleop
```

To try the viewer without a controller or tracking software:

```powershell
source-leap teleop --demo
```

For hand data in the terminal, run `source-leap`. Stop with **Ctrl+C**.
If your shell cannot find `source-leap`, use `python -m source_robotics_leap_motion`
in its place, with the same arguments.

<details>
<summary>Use an isolated Python virtual environment (optional)</summary>

Run these commands in a folder of your choice. Activation is not required:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade source-robotics-leap-motion
.\.venv\Scripts\source-leap.exe setup
.\.venv\Scripts\source-leap.exe teleop
```

Use `.\.venv\Scripts\source-leap.exe teleop` on later runs.

</details>

**Linux/macOS:** Install the compatible vendor tracking service for your platform,
then install our package with pip. Automatic runtime/driver setup currently targets
Windows x64. Linux/macOS hardware use is experimental; see
[installation and platforms](https://github.com/Source-Robotics/Source-Robotics-Leap-Motion/blob/main/docs/INSTALLATION_PLATFORMS.md).

## Read hand data in Python

```python
from source_robotics_leap_motion import Tracker

with Tracker() as tracker:  # Tracker.demo() works without a controller
    for frame in tracker:
        if hand := frame.right_hand:
            print(hand.palm.position, hand.grab_strength)
```

Positions use metres. Frames include palms, wrists, fingers/bones, orientation,
handedness, and grab/pinch values where the backend supplies them. Empty-hand frames
are valid. The package also provides recording/replay, latest-frame reads with
health counters, configurable Cartesian control, and callback adapters for robot SDKs.

## Documentation

- [User guides and documentation index](https://github.com/Source-Robotics/Source-Robotics-Leap-Motion/blob/main/docs/README.md)
- [Python API, recording, and mapping](https://github.com/Source-Robotics/Source-Robotics-Leap-Motion/blob/main/docs/USAGE.md)
- [Robot adapters and teleoperation](https://github.com/Source-Robotics/Source-Robotics-Leap-Motion/blob/main/docs/TELEOPERATION.md)
- [Interpolated receiver and gripper filtering (b4)](https://github.com/Source-Robotics/Source-Robotics-Leap-Motion/blob/main/docs/RECEIVER.md)
- [Compatibility and measured validation](https://github.com/Source-Robotics/Source-Robotics-Leap-Motion/blob/main/docs/B4_VALIDATION.md)
- [Contributing and development setup](https://github.com/Source-Robotics/Source-Robotics-Leap-Motion/blob/main/CONTRIBUTING.md)

## Repository layout

```text
src/source_robotics_leap_motion/   Installable package and browser viewer
examples/                         Small tracking, mapping, and adapter examples
tests/                            Automated software checks
docs/                             User guides, architecture, and validation
docs/history/                     Archived design and demonstration material
tools/                            Release, runtime, and measurement utilities
.github/                          CI, publishing workflow, and PR template
```

The base package has no robot SDK dependency. Each real controller supplies its own
adapter and kinematics when needed. See the
[architecture guide](https://github.com/Source-Robotics/Source-Robotics-Leap-Motion/blob/main/docs/ARCHITECTURE.md) for the module boundaries
and the [contributor guide](https://github.com/Source-Robotics/Source-Robotics-Leap-Motion/blob/main/CONTRIBUTING.md) to work from source.
