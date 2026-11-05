**Installation and platforms - decision notes, 5 November 2026**

The project owner confirms redistribution permission and approved public publication
of the GitHub repository and beta release. Version 0.1.0b1 implements Windows runtime
delivery, cache selection, first-use device setup, and shared engine ownership.
The Python wheel and native runtime are separate assets. PyPI publication succeeded
through the registered Trusted Publisher, and installation by package name was verified.

**Published PyPI experience.** The beta is available by its package name:

```text
pip install source-robotics-leap-motion
source-leap
```

On first explicit launch, select the correct runtime for the operating system and
CPU, reuse a compatible running service where available, and obtain/cache the
runtime if it is missing. Check the connected camera and OS device access. If setup
is needed, offer a one-time driver/device-access setup or open the official vendor
instructions. Verify a camera frame before reporting success. Later launches should
reuse the available runtime and start tracking directly.

Setup belongs on first launch or an explicit setup command. A wheel installation
unpacks files and generates entry points; it is not an interactive OS driver setup
hook. Imports must stay free of downloads, elevation, and device connections.
[Wheel installation specification](https://packaging.python.org/en/latest/specifications/binary-distribution-format/)

**Runtime delivery.** The tested Windows payload is about 248 MB on disk and 241 MB
as ZIP deflate. PyPI's default individual-file limit is 100 MB for personal projects
and 200 MB for organization-owned projects. A wheel containing this payload would
need an increased limit. A small pip package with a versioned first-use runtime
download is the implemented delivery path. A pinned GitHub Release URL, checksums,
atomic caching, transfer resume/restart handling, and automatic discovery are now
implemented. With driver files and notices, the release asset is about 244 MB
compressed and 251 MB extracted. Download delivery does not reduce disk footprint.
[PyPI storage limits](https://docs.pypi.org/project-management/storage-limits/)

A bundled runtime wheel remains an alternative after a suitable upload limit is
available. Each native payload must have the correct platform/architecture tag.

**Original Leap Motion Controller platform targets.**

| Platform | Vendor availability | This project's current status |
| --- | --- | --- |
| Windows x64 | Hyperion 6.2.0; archived 3.2.1 also listed | Private 3.2.1 engine, delivery/cache reuse, client sharing, restart and crash cleanup verified. Clean-PC driver setup pending. |
| Ubuntu 22.04 x86_64/amd64 | Hyperion 6.2.0; native Linux packages | Experimental native loader and setup guidance implemented; use an installed vendor service. Hardware testing pending. |
| macOS 11+, Intel | Hyperion 6.2.0 Intel download | Experimental native loader and setup guidance implemented. Hardware testing pending. |
| macOS 11+, Apple Silicon | Hyperion 6.2.0 Apple Silicon download | Experimental native loader and setup guidance implemented. Hardware testing pending. |

These vendor targets come from the Original controller's download page. They are not
claims that our current Windows implementation works on those other platforms.
[Original controller downloads](https://www.ultraleap.com/downloads/leap-controller/)

The managed launcher currently uses a Windows executable, Windows jobs, and Windows
process flags. The native LeapC backend now selects WinDLL on Windows and CDLL on
Linux/macOS, with platform-specific discovery and background-frame policy. Linux
and macOS use their own installed vendor engine/library; the Windows archive cannot
be installed on those platforms.
The common Python frame, mapping, and recording interfaces should remain the same.
Cross-platform hardware support must be tested before advertising it.

Linux's documented target is Ubuntu 22.04 on amd64, not arbitrary distributions or
Raspberry Pi/ARM. The vendor provides `ultraleap-hand-tracking-service` separately
from the control panel and OpenXR packages. A service-only setup is a useful initial
Linux path. OS package/device-access setup may still require administrator approval.
[Official Linux installation and packages](https://docs.ultraleap.com/linux/index.html)

For Windows, the locally installed runtime contains USB INF/CAT files and driver
installation helpers. A driver-only distribution must be tested on a clean machine.
An unplugged camera must not be diagnosed as a missing driver solely because no
frames arrived. The generic vendor download link offers the complete tracking suite;
it is a fallback instruction path, not evidence of a ready driver-only download.

The remaining hardware installation checks are clean-PC driver-only validation
and Linux/macOS real-device validation. No Windows driver was replaced
on this already working PC.
