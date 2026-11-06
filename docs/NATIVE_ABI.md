> Versioned historical evidence: this report describes the release or prototype
> named below. For current status, see [b3 acceptance](B3_VALIDATION.md) and the
> [documentation index](README.md).

**Native backend verification - 5 November 2026**

The native backend uses `ctypes.WinDLL` for the Windows `LEAP_CALL` calling convention,
explicit argument/return declarations, and packed structures. It is restricted to
Windows x64 in this alpha. `LeapCloseConnection` and `LeapDestroyConnection` return
void in the checked header.

Declarations were checked against `LeapSDK/include/LeapC.h` extracted from Ultraleap's
official Windows 6.2.0 installer. The installer had a valid Authenticode signature
from Ultraleap Limited. It was extracted without being executed. The extracted SDK
is development material under `.tools/sdk`, excluded from package distributions.
The large installer download was removed after extraction.

Source download:
https://s3.eu-west-1.amazonaws.com/downloads.ultraleap.com/software/tracking-software/6.2.0/tracking-software-windows-6.2.0.exe

Header SHA-256:
`27d512f953bc7dcf2d52475e5e771519b9905bc4d9a88641b1877c2897641765`

Client DLL SHA-256:
`a1127ed0b573a9431a50d8249ac21c7440e6480014b3fbc683225d90d87145f8`

The SDK header specifies packing of 1 byte. The expected x64 layout is:

| Structure | Size in bytes |
| --- | --- |
| LEAP_VECTOR | 12 |
| LEAP_QUATERNION | 16 |
| LEAP_BONE | 44 |
| LEAP_DIGIT | 184 |
| LEAP_PALM | 80 |
| LEAP_HAND | 1084 |
| LEAP_FRAME_HEADER | 24 |
| LEAP_TRACKING_EVENT | 48 |
| LEAP_CONNECTION_MESSAGE | 20 |

Important hand offsets are palm 40, digits 120, and arm 1040. Tests check these
contracts and exercise full copying, nested skeleton ownership, unit conversion,
invalid arrays, invalid numeric data, and empty-hand frames. No returned Python
object depends on message memory that the next native poll may invalidate.

These checks are header review and Python layout/conversion tests, not a compiled C
layout comparison or proof of actual hand tracking through this DLL. Loading the
6.2.0 client succeeded on CPython 3.15.2, but it did not connect to the installed
legacy 3.2.1 service. Full native-frame and reconnect validation remain outstanding.

The service's legacy WebSocket endpoint separately negotiated protocol 6 with service
version `3.2.1+45911`. The legacy backend uses that public local protocol through
`websocket-client`, with no Python extension or old interpreter. Tests exercise
decoding, palm rotation conventions, skeleton unit conversion, fallback selection,
and missing-data representation. After the user connected the Original Leap Motion
Controller, a 30-second live check captured 3,399 frames, including 53 frames with a
left hand and a complete finger skeleton. Recording and replay passed. This verifies
the legacy backend on actual hardware; it does not establish native LeapC streaming.
See [HARDWARE_VALIDATION.md](HARDWARE_VALIDATION.md).

Protocol references: [LeapJS connection](https://github.com/leapmotion/leapjs/blob/master/lib/connection/base.js),
[Ultraleap LeapC structures](https://docs.ultraleap.com/api-reference/tracking-api/group/group___structs.html).
