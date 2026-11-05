"""Device-aware first-use setup; system changes require an explicit action."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from .delivery import cached_runtime, load_catalog
from .errors import RuntimeNotFoundError
from .paths import platform_key
from .runtime import DOWNLOAD_URL, diagnose
from .runtime_bundle import inspect_runtime

LINUX_URL = "https://docs.ultraleap.com/linux/index.html"


def device_status() -> dict:
    if sys.platform != "win32":
        return {"status": "unknown", "note": "Use a live tracking probe to verify device access."}
    script = r"""$ErrorActionPreference = 'Stop'
@(Get-PnpDevice -PresentOnly | Where-Object {
    $_.InstanceId -match 'VID_F182|VID_2936|VID_05A9&PID_F580'
} | ForEach-Object {
    $code = Get-PnpDeviceProperty -InstanceId $_.InstanceId `
        -KeyName 'DEVPKEY_Device_ProblemCode' -ErrorAction SilentlyContinue
    [pscustomobject]@{ name=$_.FriendlyName; status=$_.Status; problem_code=$code.Data }
}) | ConvertTo-Json -Compress
"""
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode:
            return {"status": "unknown", "note": "Windows did not permit device inspection."}
        devices = json.loads(result.stdout or "[]") or []
        if isinstance(devices, dict):
            devices = [devices]
        if not devices:
            return {"status": "not-connected", "devices": []}
        if any(item.get("problem_code") == 28 for item in devices):
            status = "driver-required"
        elif any(item.get("problem_code") not in (0, None) for item in devices):
            status = "device-error"
        else:
            status = "present"
        return {"status": status, "devices": devices}
    except (OSError, ValueError, TypeError, AttributeError, subprocess.TimeoutExpired):
        return {"status": "unknown", "note": "Device inspection was unavailable."}


def setup_report() -> dict:
    diagnostics = diagnose()
    cached = cached_runtime()
    available = platform_key() in load_catalog()["runtimes"]
    instructions = {
        "win32": [
            "Connect the Original Leap Motion Controller directly to a USB port.",
            "If Windows reports a missing driver, run source-leap setup --install-driver.",
        ],
        "linux": [
            "Install the vendor core service for Ubuntu 22.04 amd64 using its APT instructions.",
            "The service-only package is ultraleap-hand-tracking-service; the GUI is optional.",
            "Start the vendor service and run source-leap doctor --probe.",
        ],
        "darwin": [
            "Install the matching Intel or Apple Silicon vendor hand-tracking software.",
            "Start its tracking service and grant OS access when requested.",
            "Run source-leap doctor --probe.",
        ],
    }.get(sys.platform, ["This operating system has not been integrated."])
    return {
        "platform": platform_key(),
        "native_library": diagnostics.library,
        "cached_runtime": str(cached) if cached else None,
        "automatic_download_configured": available,
        "device": device_status(),
        "instructions": instructions,
        "download_url": LINUX_URL if sys.platform == "linux" else DOWNLOAD_URL,
        "validation_note": (
            "Legacy Windows x64 tracking is tested; clean-PC driver setup is pending."
            if platform_key() == "windows-x86_64"
            else "Native integration is experimental; platform hardware testing is pending."
        ),
    }


def install_windows_driver(directory: str | Path) -> list[dict]:
    if sys.platform != "win32":
        raise RuntimeNotFoundError(
            "The driver installer is Windows-only; follow the platform setup instructions"
        )
    directory = Path(directory).resolve()
    inspect_runtime(directory)
    if device_status()["status"] != "driver-required":
        raise RuntimeNotFoundError(
            "Windows has not identified a missing Leap driver. Connect the controller and run "
            "source-leap setup. Existing working drivers are not replaced."
        )
    files = [directory / "Drivers" / name for name in ("cyfx3.inf", "ov580.inf")]
    if not all(path.is_file() for path in files):
        raise RuntimeNotFoundError(
            "This runtime archive has no driver files. Use the official download page."
        )
    tool = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/pnputil.exe"
    results = []
    for driver in files:
        arguments = subprocess.list2cmdline(["/add-driver", str(driver), "/install"])

        def literal(value):
            return "'" + str(value).replace("'", "''") + "'"

        script = (
            "$ErrorActionPreference='Stop'; $p=Start-Process -FilePath "
            + literal(tool)
            + " -ArgumentList "
            + literal(arguments)
            + " -Verb RunAs -WindowStyle Hidden -Wait -PassThru; exit $p.ExitCode"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
        )
        if result.returncode not in (0, 3010):
            raise RuntimeNotFoundError(
                f"Windows driver setup failed or approval was canceled (code {result.returncode}). "
                "Use the official vendor setup instructions."
            )
        results.append({"driver": driver.name, "reboot_required": result.returncode == 3010})
    return results
