**Release preparation for 0.1.0b1**

The source target is `Source-Robotics/Source-Robotics-Leap-Motion`. The owner explicitly
approved making it public and publishing the beta. Keep future publication gated on
anonymous availability of the pinned runtime asset. A draft release can be prepared
first; publication makes its asset available to ordinary package users.

The local release outputs are:

```text
dist/source_robotics_leap_motion-0.1.0b1-py3-none-any.whl
dist/source_robotics_leap_motion-0.1.0b1.tar.gz
dist/runtime/source-leap-runtime-windows-x86_64-3.2.1.zip
dist/runtime/runtime-descriptor.json
dist/runtime/SHA256SUMS
```

The runtime asset contains the tested engine, model, firmware, VC++ support libraries,
original USB INF/CAT files and dependencies, and notices. It excludes GUI programs,
camera recordings, user configuration, certificates, and private keys. The Python
wheel excludes all vendor executables, DLLs, and model files.

To regenerate assets from the locally cleared runtime:

```powershell
.\.venv\Scripts\python.exe tools\build_runtime_release.py .tools\private-runtime-321 --output dist\runtime --drivers "C:\Program Files (x86)\Leap Motion\Core Services\Drivers" --notice docs\VENDOR_NOTICE.txt
.\.venv\Scripts\python.exe tools\configure_release.py https://github.com/Source-Robotics/Source-Robotics-Leap-Motion --tag v0.1.0b1
.\.venv\Scripts\python.exe -m build --no-isolation
```

The configured catalog pins the exact archive bytes. Regenerating the ZIP can change
its hash; rerun configuration and rebuild the wheel whenever the archive changes.
Upload the runtime ZIP under its exact filename to the `v0.1.0b1` GitHub release.

After the runtime is publicly accessible:

```powershell
.\.venv\Scripts\python.exe tools\check_release.py
```

This verifies the public asset size and the Python wheel's contents. Runtime downloads
also verify the full pinned hash during setup; the release HEAD check alone is not
the authenticity check. Test a clean-machine first launch before declaring the
driver-only setup verified.

For PyPI, configure a Trusted Publisher for:

```text
Project: source-robotics-leap-motion
Owner: Source-Robotics
Repository: Source-Robotics-Leap-Motion
Workflow: publish.yml
Environment: pypi
```

No long-lived PyPI token is required by the prepared workflow. The PyPI account owner
must authorize the publisher (a pending publisher can create the first project).
The manually triggered publication workflow runs tests, downloads the exact existing
GitHub release wheel/sdist, verifies their GitHub SHA-256 digests, checks metadata and
public runtime availability, then publishes those same bytes through OIDC.
[PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/)

The CI workflow tests installed packages on Windows/Linux/macOS. Hosted runners have
no Leap controller: passing CI verifies software behavior and layout, not device
support on every platform. Keep hardware results separate in the validation report.
