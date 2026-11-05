"""Reuse an existing service, or lease a private engine shared by local clients."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

from .._locking import file_lock
from ..errors import ConnectionError
from ..paths import cache_root
from ..runtime_bundle import inspect_runtime
from .legacy import LegacyWebSocketBackend
from .managed import _port_in_use


def _lease(state: Path):
    connection = None
    try:
        data = json.loads((state / "broker.json").read_text())
        if type(data["port"]) is not int or not 1 <= data["port"] <= 65535:
            return None
        connection = socket.create_connection(("127.0.0.1", data["port"]), timeout=0.5)
        connection.sendall(json.dumps({"token": data["token"]}).encode() + b"\n")
        response = b""
        while not response.endswith(b"\n") and len(response) < 1024:
            chunk = connection.recv(1024)
            if not chunk:
                break
            response += chunk
        if json.loads(response).get("ready") is True:
            return connection
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    if connection is not None:
        connection.close()
    return None


class SharedRuntimeBackend:
    name = "managed-legacy"

    def __init__(self, directory, *, connect_timeout=10):
        self.directory = Path(directory).resolve()
        self.connect_timeout = max(connect_timeout, 10)
        self._connection = None
        self._backend = None
        self._mode = None

    @property
    def details(self):
        return {"mode": self._mode, "directory": str(self.directory)}

    def open(self):
        if self._backend is not None:
            raise RuntimeError("Shared tracking is already open")
        inspect_runtime(self.directory, verify=False)
        root = cache_root()
        state = root / "engine"
        try:
            with file_lock(root / "engine.lock", timeout=self.connect_timeout + 5):
                self._connection = _lease(state)
                if self._connection is None and not _port_in_use():
                    state.mkdir(parents=True, exist_ok=True)
                    # Only coordinator-owned state; stale credentials cannot identify a live lease.
                    (state / "broker.json").unlink(missing_ok=True)
                    with (state / "broker-output.log").open("ab") as output:
                        child = subprocess.Popen(
                            [
                                sys.executable,
                                "-m",
                                "source_robotics_leap_motion._broker",
                                "--directory",
                                str(self.directory),
                                "--state",
                                str(state),
                                "--timeout",
                                str(self.connect_timeout),
                            ],
                            stdin=subprocess.DEVNULL,
                            stdout=output,
                            stderr=subprocess.STDOUT,
                            creationflags=subprocess.CREATE_NO_WINDOW
                            if sys.platform == "win32"
                            else 0,
                            start_new_session=sys.platform != "win32",
                        )
                    deadline = time.perf_counter() + self.connect_timeout + 2
                    while self._connection is None:
                        self._connection = _lease(state)
                        if self._connection is not None:
                            break
                        if child.poll() is not None or time.perf_counter() >= deadline:
                            raise ConnectionError(
                                "Private engine coordinator did not become ready. "
                                f"See {state / 'broker-output.log'}"
                            )
                        time.sleep(0.05)
                self._mode = "shared-private" if self._connection is not None else "existing"
                self._backend = LegacyWebSocketBackend(connect_timeout=self.connect_timeout)
                self._backend.open()
        except BaseException:
            self.close()
            raise

    def read(self, timeout):
        if self._backend is None:
            raise RuntimeError("Shared tracking is not open")
        return self._backend.read(timeout)

    def close(self):
        try:
            if self._backend is not None:
                self._backend.close()
        finally:
            self._backend = None
            if self._connection is not None:
                self._connection.close()
                self._connection = None
