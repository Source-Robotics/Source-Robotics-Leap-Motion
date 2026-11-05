"""Prepare a local legacy runtime for experiments; never downloads vendor assets."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

from .errors import RuntimeNotFoundError

SCHEMA = "source-robotics-leap-motion/local-runtime"
MANIFEST = "runtime-manifest.json"
ENGINE = "LeapSvc64.exe"
CORE_FILES = (
    ENGINE,
    "Tracking.ldat",
    "CyBootProgrammer.ldat",
    "CyPeripheral.ldat",
    "CyUVCBootstrap.ldat",
)
DEPENDENCIES = ("msvcp120.dll", "msvcr120.dll")
OPTIONAL_MODELS = ("Tracking-desktop.ldat", "Tracking-1202.ldat")
DRIVER_FILES = (
    "Drivers/cyfx3.inf",
    "Drivers/cyfx3.cat",
    "Drivers/ov580.inf",
    "Drivers/ov580.cat",
    "Drivers/WdfCoInstaller01011.dll",
    "Drivers/winusbcoinstaller2.dll",
)
ALLOWED_FILES = frozenset(
    CORE_FILES + DEPENDENCIES + OPTIONAL_MODELS + DRIVER_FILES + ("NOTICE.txt",)
)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_local_runtime(
    source: str | Path,
    destination: str | Path,
    *,
    dependency_dir: str | Path | None = None,
    extra_models: bool = False,
) -> dict:
    """Copy an explicit allowlist from an existing installation, with no GUI files.

    This is a local-development operation. It establishes no redistribution rights.
    Existing matching files can be adopted; differing files are never overwritten.
    """
    source = Path(source).resolve()
    destination = Path(destination).resolve()
    if source == destination:
        raise ValueError("Choose a separate destination for the private runtime")
    selected = list(CORE_FILES)
    if extra_models:
        selected.extend(OPTIONAL_MODELS)
    files = {name: source / name for name in selected}
    dependency_locations = [source]
    if dependency_dir is not None:
        dependency_locations.append(Path(dependency_dir).resolve())
    dependency_locations.append(Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32")
    for name in DEPENDENCIES:
        candidate = next(
            (
                directory / name
                for directory in dependency_locations
                if (directory / name).is_file()
            ),
            None,
        )
        if candidate is None:
            raise RuntimeNotFoundError(f"Missing {name}; supply its directory with --dependencies")
        files[name] = candidate
    for path in files.values():
        if not path.is_file():
            raise RuntimeNotFoundError(f"Missing legacy runtime component: {path}")
    destination.mkdir(parents=True, exist_ok=True)
    entries = []
    for name, origin in files.items():
        target = destination / name
        digest = file_hash(origin)
        if target.exists():
            if not target.is_file() or file_hash(target) != digest:
                raise FileExistsError(f"Refusing to overwrite a different runtime file: {target}")
        else:
            shutil.copyfile(origin, target)
        entries.append({"name": name, "bytes": target.stat().st_size, "sha256": digest})
    manifest = {
        "schema": SCHEMA,
        "version": 1,
        "kind": "legacy-windows-x64",
        "engine": ENGINE,
        "files": entries,
        "provenance": "local copy of an existing installation",
        "redistribution_cleared": False,
    }
    (destination / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return inspect_runtime(destination)


def inspect_runtime(directory: str | Path, *, verify: bool = True) -> dict:
    directory = Path(directory).resolve()
    try:
        manifest_path = directory / MANIFEST
        if manifest_path.stat().st_size > 64 * 1024:
            raise ValueError("Runtime manifest exceeds the size limit")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            manifest["schema"] != SCHEMA
            or manifest["version"] != 1
            or manifest["kind"] != "legacy-windows-x64"
            or manifest["engine"] != ENGINE
        ):
            raise ValueError("Unsupported runtime manifest")
        names = [entry["name"] for entry in manifest["files"]]
        if len(names) != len(set(names)) or not set(names) <= ALLOWED_FILES:
            raise ValueError("Runtime manifest contains duplicate or unsupported file names")
        if not set(CORE_FILES + DEPENDENCIES) <= set(names):
            raise ValueError("Runtime manifest is missing required components")
        total = 0
        for entry in manifest["files"]:
            path = directory / entry["name"]
            if not path.resolve().is_relative_to(directory) or not path.is_file():
                raise ValueError(f"Missing or externally linked runtime file: {entry['name']}")
            size = path.stat().st_size
            if size != entry["bytes"]:
                raise ValueError(f"Runtime file size mismatch: {entry['name']}")
            if verify and file_hash(path) != entry["sha256"]:
                raise ValueError(f"Runtime file checksum mismatch: {entry['name']}")
            total += size
        return {
            "directory": str(directory),
            "engine": str(directory / ENGINE),
            "files": len(names),
            "bytes": total,
            "redistribution_cleared": manifest.get("redistribution_cleared", False),
            "checksum_verified": verify,
        }
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise RuntimeNotFoundError(f"Invalid local runtime at {directory}: {exc}") from exc
