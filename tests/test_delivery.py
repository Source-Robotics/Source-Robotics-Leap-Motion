import hashlib
import json
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from source_robotics_leap_motion import delivery
from source_robotics_leap_motion.errors import RuntimeNotFoundError
from source_robotics_leap_motion.runtime_bundle import (
    CORE_FILES,
    DEPENDENCIES,
    MANIFEST,
    SCHEMA,
)


@pytest.fixture
def runtime_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(delivery, "platform_key", lambda: "windows-x86_64")
    files = {name: (name * 3).encode() for name in CORE_FILES + DEPENDENCIES}
    manifest = {
        "schema": SCHEMA,
        "version": 1,
        "kind": "legacy-windows-x64",
        "engine": CORE_FILES[0],
        "redistribution_cleared": True,
        "files": [
            {"name": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in files.items()
        ],
    }
    archive = tmp_path / "runtime.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for name, data in files.items():
            bundle.writestr(name, data)
        bundle.writestr(MANIFEST, json.dumps(manifest))
    return archive


def test_offline_import_is_atomic_idempotent_and_uses_cache(runtime_archive, tmp_path):
    root = tmp_path / "cache"
    directory = delivery.install_archive(runtime_archive, root=root)
    assert directory.parent == root / "runtimes"
    assert delivery.cached_runtime(root=root) == directory
    assert delivery.install_archive(runtime_archive, root=root) == directory
    assert not list(directory.parent.glob(".install-*"))


@pytest.mark.parametrize("member", ["../escape.exe", "/absolute.exe", "not-allowed.exe"])
def test_archive_rejects_unexpected_or_escaping_members(runtime_archive, tmp_path, member):
    with zipfile.ZipFile(runtime_archive, "a") as bundle:
        bundle.writestr(member, b"bad")
    root = tmp_path / "cache"
    with pytest.raises(RuntimeNotFoundError, match="unsupported archive member"):
        delivery.install_archive(runtime_archive, root=root)
    assert not (root / "active.json").exists()
    assert not list((root / "runtimes").glob(".install-*"))


def test_corrupt_member_never_becomes_active(runtime_archive, tmp_path):
    replacement = tmp_path / "corrupt.zip"
    with zipfile.ZipFile(runtime_archive) as original, zipfile.ZipFile(replacement, "w") as changed:
        for member in original.infolist():
            data = original.read(member)
            if member.filename == "Tracking.ldat":
                data = b"X" + data[1:]
            changed.writestr(member, data)
    with pytest.raises(RuntimeNotFoundError, match="checksum mismatch"):
        delivery.install_archive(replacement, root=tmp_path / "cache")
    assert not (tmp_path / "cache/active.json").exists()


@pytest.fixture
def download_server(runtime_archive):
    data = runtime_archive.read_bytes()
    requests = []
    options = {"ignore_range": False, "bad_range": False}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            header = self.headers.get("Range")
            requests.append(header)
            offset = int(header.split("=")[1].split("-")[0]) if header else 0
            if header and not options["ignore_range"]:
                self.send_response(206)
                value = f"bytes {offset}-{len(data) - 1}/{len(data)}"
                self.send_header("Content-Range", "bytes 0-1/2" if options["bad_range"] else value)
            else:
                self.send_response(200)
                offset = 0
            self.send_header("Content-Length", str(len(data) - offset))
            self.end_headers()
            self.wfile.write(data[offset:])

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    entry = {
        "id": "test-runtime",
        "url": f"http://127.0.0.1:{server.server_port}/runtime.zip",
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "unpacked_bytes": 100000,
    }
    try:
        yield entry, data, requests, options
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("ignore_range", [False, True])
def test_download_resumes_or_restarts_when_server_ignores_range(
    download_server, tmp_path, ignore_range
):
    entry, data, requests, options = download_server
    options["ignore_range"] = ignore_range
    target = tmp_path / "archive.zip"
    target.with_suffix(".partial").write_bytes(data[:37])
    assert delivery._download(entry, target).read_bytes() == data
    assert requests == ["bytes=37-"]


def test_invalid_resume_response_is_rejected(download_server, tmp_path):
    entry, data, _requests, options = download_server
    options["bad_range"] = True
    target = tmp_path / "archive.zip"
    target.with_suffix(".partial").write_bytes(data[:37])
    with pytest.raises(RuntimeNotFoundError, match="Content-Range"):
        delivery._download(entry, target)
    assert not target.exists()


def test_pinned_hash_is_checked_before_extracting(download_server, tmp_path):
    entry, _data, _requests, _options = download_server
    entry["sha256"] = "0" * 64
    with pytest.raises(RuntimeNotFoundError, match="SHA-256 mismatch"):
        delivery._download(entry, tmp_path / "archive.zip")


def test_catalog_download_installs_once_and_reuses_without_network(download_server, tmp_path):
    entry, _data, requests, _options = download_server
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "schema": delivery.CATALOG_SCHEMA,
                "version": 1,
                "runtimes": {delivery.platform_key(): entry},
            }
        )
    )
    root = tmp_path / "cache"
    first = delivery.ensure_runtime(catalog=catalog, root=root)
    assert delivery.ensure_runtime(catalog=catalog, root=root) == first
    assert len(requests) == 1
    assert not list((root / "downloads").glob("*.zip"))


def test_cached_pointer_cannot_escape_cache(tmp_path):
    (tmp_path / "active.json").write_text(
        json.dumps(
            {
                "id": "../outside",
                "platform": delivery.platform_key(),
            }
        )
    )
    with pytest.raises(RuntimeNotFoundError, match="Invalid runtime cache"):
        delivery.cached_runtime(root=tmp_path)


def test_catalog_requires_secure_public_transport():
    entry = {
        "id": "valid",
        "sha256": "0" * 64,
        "bytes": 10,
        "unpacked_bytes": 20,
        "url": "http://example.com/engine.zip",
    }
    with pytest.raises(RuntimeNotFoundError, match="HTTPS"):
        delivery._descriptor(entry)
