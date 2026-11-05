**Beta 0.1.0b1 validation - 5 November 2026**

This release candidate implements automatic runtime delivery and cache selection,
shared engine ownership, first-use setup, and experimental POSIX LeapC loading.
The repository was made public with the owner's explicit approval. The GitHub beta
release is prepared with a public runtime URL; PyPI publication depends on authorizing
its Trusted Publisher. The direct GitHub wheel installation is the initial beta path.

**Windows checks.** All checks used project-local Python virtual environments.

- The 244,070,193-byte release archive was served by a local HTTP server, downloaded,
  verified against its pinned SHA-256, and installed atomically. A fresh process reused
  the cache with the server unavailable. The compressed cache copy was removed.
- Windows device inspection reported the Original controller present, with problem
  code zero. No driver installation or replacement was performed on this working PC.
- The beta wheel was installed into an isolated venv. With the installed service
  temporarily stopped, plain `Tracker()` selected the cached engine automatically.
- Two simultaneous clients acquired leases. Closing the first left the second
  receiving 30 more camera frames. Closing the last client stopped the engine.
- Two complete engine restart cycles received real camera frames and cleaned up.
- A separate client received a frame and exited abruptly without closing its tracker.
  Its lease closed automatically, and the coordinator stopped the unused engine.
- The installed service was restored, and a real-frame probe passed afterward.
  Results: `.tools/private-probes/f8562a2404a64767bc4f6202a4e9f828/summary.json`.
- The 86-test suite covers transport resume/restart, checksum failures, extraction
  validation, atomic caching, device-status distinctions, shared leases, connection
  recovery, native loading, data models, mapping, CLI behavior, and recording/replay.

The earlier hand capture remains the live skeleton evidence: 1,047 frames over ten
seconds, including 50 complete left-hand samples with arm data, about 105 FPS.
No new CPU/latency improvement is claimed by this installer/lifecycle work.

**Other platforms.** Native loading uses the vendor header's Windows calling
convention on Windows and C calling convention on Linux/macOS. The SDK structures
remain packed as specified by the vendor header. Background-frame policy is requested
explicitly. Loader selection is unit-tested. Installed library discovery includes
the documented Ubuntu paths and the macOS application SDK path.

GitHub CI is configured for Python 3.10-3.15 on Windows, Linux, and macOS. CI results
were checked on source commit `7c2f782`: every Windows and Linux Python job passed,
along with the package build and metadata checks. macOS 3.11 and 3.13 jobs passed;
other macOS jobs were still waiting for hosted runners at the time of this report.
The Windows installed-wheel matrix separately passed all 86 tests on each Python
minor version from 3.10 through 3.15, with live camera frames and private-recording replay.
No Linux or Mac hardware test has been performed on this Windows PC. Windows-managed
runtime archives are deliberately rejected on other platforms, which use an installed
native vendor service and platform-specific setup instructions.

**Remaining release checks.** A clean Windows hardware installation is still needed
to validate driver-only setup without any previous vendor installation. A working
developer PC does not provide that evidence. Linux/macOS real-device tests and long
sessions also remain. Public runtime availability and PyPI publisher configuration
are required before new users can use the short PyPI package-name installation flow.
