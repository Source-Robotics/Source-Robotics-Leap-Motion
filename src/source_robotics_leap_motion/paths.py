"""Fixed application locations; no directory searches or import-time writes."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def cache_root() -> Path:
    if override := os.environ.get("SOURCE_LEAP_CACHE"):
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
    elif sys.platform == "darwin":
        base = Path.home() / "Library/Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    return base / "source-robotics-leap-motion"


def platform_key() -> str:
    import platform

    machine = platform.machine().lower()
    architecture = {"amd64": "x86_64", "x64": "x86_64", "aarch64": "arm64"}.get(machine, machine)
    return (
        {"win32": "windows", "darwin": "macos"}.get(sys.platform, sys.platform) + "-" + architecture
    )
