"""Read-only runtime discovery. No installer hooks or directory walks."""

from __future__ import annotations

import os
import platform
import struct
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from .errors import RuntimeNotFoundError

DOWNLOAD_URL = "https://www.ultraleap.com/downloads/leap-controller/"


def library_candidates(explicit: str | Path | None = None) -> tuple[Path, ...]:
    if explicit is not None:
        return (Path(explicit).expanduser().resolve(),)
    if override := os.environ.get("SOURCE_LEAP_LIBRARY"):
        return (Path(override).expanduser().resolve(),)
    candidates: list[Path] = []
    if sdk := os.environ.get("LEAPSDK_INSTALL_LOCATION"):
        relative = {"win32": "lib/x64/LeapC.dll", "darwin": "lib/libLeapC.dylib"}.get(
            sys.platform, "lib/libLeapC.so"
        )
        candidates.append(Path(sdk) / relative)
    if sys.platform == "win32":
        program_files = Path(os.environ.get("ProgramFiles", "C:/Program Files"))
        candidates.append(program_files / "Ultraleap/LeapSDK/lib/x64/LeapC.dll")
    elif sys.platform == "darwin":
        candidates.append(
            Path("/Applications/Ultraleap Hand Tracking.app/Contents/LeapSDK/lib/libLeapC.dylib")
        )
    else:
        candidates.extend(
            Path(path)
            for path in (
                "/usr/lib/ultraleap-hand-tracking-service/libLeapC.so",
                "/usr/lib/x86_64-linux-gnu/libLeapC.so",
                "/usr/share/doc/ultraleap-hand-tracking-service/libLeapC.so",
                "/opt/ultraleap/LeapSDK/lib/libLeapC.so",
            )
        )
    return tuple(dict.fromkeys(candidates))


def find_library(explicit: str | Path | None = None) -> Path:
    candidates = library_candidates(explicit)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    searched = ", ".join(str(path) for path in candidates)
    raise RuntimeNotFoundError(
        "LeapC client library was not found. Install the compatible Ultraleap tracking "
        f"software for the Original Leap Motion Controller: {DOWNLOAD_URL}\n"
        "The old Leap.dll / LeapPython.pyd cannot be used by this package.\n"
        f"Checked: {searched}"
    )


def _service_executable() -> str | None:
    if sys.platform != "win32":
        return None
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\LeapService"
        ) as key:
            return winreg.QueryValueEx(key, "ImagePath")[0]
    except OSError:
        return None


@dataclass(frozen=True, slots=True)
class RuntimeReport:
    python: str
    executable: str
    platform: str
    architecture_bits: int
    library: str | None
    checked_paths: tuple[str, ...]
    service_executable: str | None
    notes: tuple[str, ...]
    cached_runtime: str | None = None
    download_url: str = DOWNLOAD_URL

    def to_dict(self) -> dict:
        return asdict(self)


def diagnose(library_path: str | None = None) -> RuntimeReport:
    from .delivery import cached_runtime

    candidates = library_candidates(library_path)
    library = next((str(path.resolve()) for path in candidates if path.is_file()), None)
    service = _service_executable()
    notes = []
    try:
        cached = cached_runtime()
    except RuntimeNotFoundError as exc:
        cached = None
        notes.append(str(exc))
    if library is None:
        notes.append(
            "LeapC client missing; auto mode can still try the local legacy WebSocket service."
        )
    if service and "leap motion" in service.lower():
        notes.append(
            "A legacy Leap Motion service installation was detected. "
            "A current LeapC client alone does not update that service."
        )
    if sys.platform != "win32" or struct.calcsize("P") != 8:
        notes.append("Linux/macOS native support is experimental; hardware validation is pending.")
    notes.append("Library discovery does not prove service or camera connectivity; use --probe.")
    return RuntimeReport(
        python=platform.python_version(),
        executable=sys.executable,
        platform=platform.platform(),
        architecture_bits=struct.calcsize("P") * 8,
        library=library,
        checked_paths=tuple(str(path) for path in candidates),
        service_executable=service,
        notes=tuple(notes),
        cached_runtime=str(cached) if cached else None,
    )
