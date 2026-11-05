"""Pinned runtime downloads, resumable transfers, validated extraction, and caching."""

from __future__ import annotations

import http.client
import json
import logging
import os
import re
import shutil
import stat
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from ._locking import file_lock
from .errors import RuntimeNotFoundError
from .paths import cache_root, platform_key
from .runtime_bundle import ALLOWED_FILES, MANIFEST, file_hash, inspect_runtime

CATALOG_SCHEMA = "source-robotics-leap-motion/catalog"
MAX_PAYLOAD = 2 * 1024**3


def _write_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + "." + os.urandom(6).hex() + ".tmp")
    try:
        temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load_catalog(path: str | Path | None = None) -> dict:
    selected = path or os.environ.get("SOURCE_LEAP_CATALOG")
    source = Path(selected) if selected else Path(__file__).with_name("runtime_catalog.json")
    try:
        if source.stat().st_size > 65536:
            raise ValueError("catalog exceeds size limit")
        data = json.loads(source.read_text(encoding="utf-8"))
        if data["schema"] != CATALOG_SCHEMA or data["version"] != 1:
            raise ValueError("unsupported catalog")
        if not isinstance(data["runtimes"], dict):
            raise ValueError("runtimes must be an object")
        return data
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise RuntimeNotFoundError(f"Cannot read runtime catalog: {exc}") from exc


def _descriptor(data: dict) -> dict:
    try:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,59}", data["id"]):
            raise ValueError("invalid runtime id")
        if not re.fullmatch(r"[0-9a-f]{64}", data["sha256"]):
            raise ValueError("invalid SHA-256")
        for name in ("bytes", "unpacked_bytes"):
            if type(data[name]) is not int or not 0 < data[name] <= MAX_PAYLOAD:
                raise ValueError(f"invalid {name}")
        parsed = urllib.parse.urlsplit(data["url"])
        local_test = parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost")
        if not (parsed.scheme == "https" or local_test) or not parsed.hostname:
            raise ValueError("runtime downloads require HTTPS")
        if parsed.username or parsed.password or parsed.fragment:
            raise ValueError("credentials/fragments are not allowed in download URLs")
        return data
    except (KeyError, ValueError, TypeError) as exc:
        raise RuntimeNotFoundError(f"Invalid runtime download descriptor: {exc}") from exc


def _download(entry: dict, target: Path, progress=None) -> Path:
    partial = target.with_suffix(".partial")
    if target.exists():
        if target.stat().st_size == entry["bytes"] and file_hash(target) == entry["sha256"]:
            return target
        target.unlink()
    offset = partial.stat().st_size if partial.exists() else 0
    if offset > entry["bytes"]:
        partial.unlink()
        offset = 0
    if offset == entry["bytes"]:
        if file_hash(partial) == entry["sha256"]:
            partial.replace(target)
            return target
        partial.unlink()
        offset = 0
    headers = {"User-Agent": "source-robotics-leap-motion", "Accept-Encoding": "identity"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    try:
        logging.getLogger(__name__).info(
            "Downloading tracking runtime: %.1f MB%s",
            entry["bytes"] / 1_000_000,
            " (resuming)" if offset else "",
        )
        request = urllib.request.Request(entry["url"], headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            final_url = urllib.parse.urlsplit(response.geturl())
            initial_url = urllib.parse.urlsplit(entry["url"])
            if initial_url.scheme == "https" and final_url.scheme != "https":
                raise ValueError("download redirected away from HTTPS")
            if response.status == 206:
                expected = f"bytes {offset}-{entry['bytes'] - 1}/{entry['bytes']}"
                if response.headers.get("Content-Range") != expected:
                    partial.unlink(missing_ok=True)
                    raise ValueError("invalid resumed Content-Range")
            elif response.status == 200:
                offset = 0  # A server may ignore Range; restart instead of appending.
            else:
                raise ValueError(f"unexpected HTTP status {response.status}")
            with partial.open("ab" if offset else "wb") as stream:
                received = offset
                while chunk := response.read(1024 * 1024):
                    received += len(chunk)
                    if received > entry["bytes"]:
                        raise ValueError("download exceeds its pinned size")
                    stream.write(chunk)
                    if progress is not None:
                        progress(received, entry["bytes"])
        if partial.stat().st_size != entry["bytes"]:
            raise OSError("Download interrupted; run setup again to resume")
        if file_hash(partial) != entry["sha256"]:
            partial.unlink()
            raise ValueError("runtime archive SHA-256 mismatch")
        partial.replace(target)
        return target
    except (OSError, ValueError, http.client.HTTPException) as exc:
        raise RuntimeNotFoundError(f"Runtime download failed: {exc}") from exc


def _extract(archive: Path, destination: Path, maximum: int) -> None:
    try:
        with zipfile.ZipFile(archive) as bundle:
            members = bundle.infolist()
            names = [member.filename for member in members]
            if len(names) != len(set(names)) or MANIFEST not in names:
                raise ValueError("missing manifest or duplicate archive members")
            if not set(names) <= ALLOWED_FILES | {MANIFEST}:
                raise ValueError("unsupported archive member")
            manifest_info = bundle.getinfo(MANIFEST)
            if manifest_info.file_size > 65536:
                raise ValueError("manifest exceeds size limit")
            manifest = json.loads(bundle.read(MANIFEST))
            entries = manifest["files"]
            sizes = {entry["name"]: entry["bytes"] for entry in entries}
            if len(sizes) != len(entries) or set(names) != set(sizes) | {MANIFEST}:
                raise ValueError("archive contents differ from its manifest")
            if any(type(size) is not int or size < 0 for size in sizes.values()):
                raise ValueError("invalid uncompressed size")
            if sum(sizes.values()) > maximum:
                raise ValueError("uncompressed payload exceeds its size limit")
            for member in members:
                if member.flag_bits & 1 or stat.S_ISLNK(member.external_attr >> 16):
                    raise ValueError("encrypted or linked archive member")
                expected = (
                    manifest_info.file_size
                    if member.filename == MANIFEST
                    else sizes[member.filename]
                )
                if member.file_size != expected:
                    raise ValueError("archive member size mismatch")
                target = destination / member.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(member) as origin, target.open("xb") as output:
                    shutil.copyfileobj(origin, output, 1024 * 1024)
        inspect_runtime(destination, verify=True)
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        raise RuntimeNotFoundError(f"Invalid runtime archive: {exc}") from exc


def _install(archive: Path, root: Path, runtime_id: str, maximum: int) -> Path:
    if platform_key() != "windows-x86_64":
        raise RuntimeNotFoundError(
            "Managed runtime archives currently target Windows x64. "
            "Run source-leap setup for this platform's native service instructions."
        )
    destination = root / "runtimes" / runtime_id
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        inspect_runtime(destination)
    else:
        staging = Path(tempfile.mkdtemp(prefix=".install-", dir=destination.parent))
        try:
            _extract(archive, staging, maximum)
            staging.replace(destination)
        finally:
            if staging.exists():
                if staging.resolve().parent != destination.parent.resolve():
                    raise RuntimeNotFoundError(
                        "Refusing cleanup outside the runtime staging directory"
                    )
                shutil.rmtree(staging)  # mkdtemp path under our explicit runtimes directory.
    _write_json(root / "active.json", {"id": runtime_id, "platform": platform_key()})
    return destination


def install_archive(archive: str | Path, *, root: Path | None = None) -> Path:
    """Explicit offline import. The local file is trusted by the caller, then validated."""
    archive = Path(archive).resolve()
    if not archive.is_file() or archive.stat().st_size > MAX_PAYLOAD:
        raise RuntimeNotFoundError("Runtime archive is missing or too large")
    root = (root or cache_root()).resolve()
    runtime_id = "local-" + file_hash(archive)[:24]
    with file_lock(root / "setup.lock"):
        return _install(archive, root, runtime_id, MAX_PAYLOAD)


def cached_runtime(*, root: Path | None = None) -> Path | None:
    root = root or cache_root()
    try:
        data = json.loads((root / "active.json").read_text(encoding="utf-8"))
        if data["platform"] != platform_key() or not re.fullmatch(
            r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}", data["id"]
        ):
            raise ValueError("invalid cached runtime selection")
        directory = root / "runtimes" / data["id"]
        inspect_runtime(directory, verify=False)
        return directory
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeNotFoundError(f"Invalid runtime cache; run source-leap setup: {exc}") from exc


def ensure_runtime(
    *, catalog: str | Path | None = None, root: Path | None = None, progress=None
) -> Path:
    root = (root or cache_root()).resolve()
    if (existing := cached_runtime(root=root)) is not None:
        return existing
    data = load_catalog(catalog)
    selected = data["runtimes"].get(platform_key())
    if selected is None:
        raise RuntimeNotFoundError(
            f"No automatic runtime download is configured for {platform_key()} in this build. "
            "Run 'source-leap setup' for device setup or use 'source-leap setup --archive PATH' "
            "with the release's offline runtime archive."
        )
    entry = _descriptor(selected)
    with file_lock(root / "setup.lock", timeout=180):
        if (existing := cached_runtime(root=root)) is not None:
            return existing
        downloads = root / "downloads"
        downloads.mkdir(parents=True, exist_ok=True)
        archive = _download(entry, downloads / (entry["sha256"] + ".zip"), progress)
        result = _install(
            archive, root, entry["id"] + "-" + entry["sha256"][:12], entry["unpacked_bytes"]
        )
        archive.unlink(missing_ok=True)  # Keep one extracted copy, not a second 241 MB archive.
        return result
