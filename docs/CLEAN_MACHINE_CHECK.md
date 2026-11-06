**Clean Windows installation acceptance — Original Leap Motion Controller**

This check requires a separate Windows x64 PC with no previous Leap/Ultraleap
installation or driver. A fresh venv on the development PC does not provide that
evidence. Hosted CI verifies clean software installation and simulated behavior,
but has no USB controller attached.

Use a supported 64-bit CPython 3.10–3.15 installation. Create a fresh venv outside
the source checkout, then install by package name from PyPI. Record the actual
package version before testing.

```powershell
python -m venv leap-check
.\leap-check\Scripts\python.exe -m pip install source-robotics-leap-motion
.\leap-check\Scripts\source-leap.exe --version
.\leap-check\Scripts\source-leap.exe teleop --demo --headless --auto-arm --frames 30
.\leap-check\Scripts\source-leap.exe doctor --json
```

The demo command requires b3 or later. If it is not yet published, use the prepared
release-candidate wheel explicitly and record that fact; a local-wheel test is not
the same as verifying the public package-name installation.

Follow these steps with the physical controller:

1. Start with the camera unplugged. Run `source-leap setup --json`. It should report
   the absent camera distinctly from a missing driver; it must not install a driver
   just because no frames arrived.
2. Plug in the Original controller. Inspect setup's device status. If Windows reports
   a missing driver, run `source-leap setup --install-driver` and approve Windows'
   administrator prompt. Record the driver publisher/version and every manual step.
3. Run `source-leap doctor --probe --json`, then `source-leap --latest --health --duration 10`.
   Confirm live frames with no hands, then full hand data when a hand is visible.
4. Run `source-leap teleop`. Arm, clutch, resume, remove the hand, and return it.
   Confirm a returning hand stays held until explicit rearming. Output goes to the
   simulated Cartesian arm.
5. Close all package clients. Confirm the private engine shuts down after its final
   client. Reopen tracking and repeat the frame probe. Check repeated startups and
   one abrupt client exit.
6. Reuse the populated cache with network access unavailable. Tracking should work
   without another download. Reboot and repeat the probe to verify driver persistence.

Keep the console reports locally. Capture the package/interpreter versions, whether a vendor
service was present, runtime download/cache behavior, device/driver state, live frame
and skeleton counts, shutdown/restart outcome, and any unexpected errors.

Passing means the package installs without a compiler or Python 3.8, first use obtains
the pinned runtime, setup diagnoses the device correctly, the minimum driver path
works, and tracking/restart/cache reuse succeed. A GUI vendor installation used to
make the test work must be recorded as an additional prerequisite rather than called
driver-only success.

**Current evidence.** Package-name installation and live frames were verified in fresh
project-local venvs on an already working Windows PC. Private-engine startup/sharing/
crash cleanup was tested separately with its existing driver. No separate clean
Windows USB installation has passed yet. This PC has no Windows Sandbox executable,
no installed WSL distribution, and no running Docker engine. Linux/macOS USB and actual
robot-controller checks also remain pending; their software CI results are separate.
