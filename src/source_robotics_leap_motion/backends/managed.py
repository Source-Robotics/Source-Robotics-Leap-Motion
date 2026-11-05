"""On-demand local legacy engine. Never installs, stops, or modifies system services."""

from __future__ import annotations

import json
import math
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

from ..errors import ConnectionError, RuntimeNotFoundError
from ..runtime_bundle import inspect_runtime
from .legacy import LegacyWebSocketBackend


def _port_in_use() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 6437), timeout=0.25):
            return True
    except OSError:
        return False


class ManagedLegacyBackend:
    name = "managed-legacy"

    def __init__(
        self,
        directory: str | Path,
        *,
        connect_timeout: float = 10,
        reuse_existing: bool = True,
        state_dir: str | Path | None = None,
    ):
        if not math.isfinite(connect_timeout) or connect_timeout <= 0:
            raise ValueError("Connection timeout must be positive and finite")
        self.directory = Path(directory).resolve()
        self.connect_timeout = connect_timeout
        self.reuse_existing = reuse_existing
        self.state_dir = (
            Path(state_dir).resolve() if state_dir is not None else self.directory / "state"
        )
        self.reused_existing = False
        self._backend = None
        self._pending_frame = None
        self._process = None
        self._job = None
        self._log = None

    @property
    def details(self) -> dict:
        return {
            "mode": "existing" if self.reused_existing else "private",
            "directory": str(self.directory),
            "pid": self._process.pid if self._process is not None else None,
        }

    def open(self) -> None:
        if self._backend is not None or self._process is not None:
            raise RuntimeError("Managed runtime is already open")
        if sys.platform != "win32" or struct.calcsize("P") != 8:
            raise RuntimeNotFoundError("The managed legacy runtime prototype requires Windows x64")
        inspect_runtime(self.directory, verify=False)
        self.reused_existing = False
        if _port_in_use():
            if not self.reuse_existing:
                raise ConnectionError(
                    "Port 6437 is already in use. Exclusive private testing requires the existing "
                    "Leap service to be stopped first. This launcher never stops system services."
                )
            existing = LegacyWebSocketBackend(connect_timeout=self.connect_timeout)
            try:
                existing.open()
            except BaseException:
                existing.close()
                raise
            self._backend = existing
            self.reused_existing = True
            return
        bundle = inspect_runtime(self.directory, verify=True)
        state = self.state_dir
        state.mkdir(parents=True, exist_ok=True)
        config = state / "config.json"
        config.write_text(
            json.dumps(
                {
                    "configuration": {
                        "websockets_enabled": True,
                        "websockets_allow_remote": False,
                        "background_app_mode": 2,
                        "images_mode": 0,
                        "api_namespace": "source_robotics_private",
                    }
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        try:
            from ._job import ProcessJob

            self._job = ProcessJob()
            self._log = (state / "engine-output.log").open("ab")
            self._process = subprocess.Popen(
                [bundle["engine"], "--run", "--config=" + str(config)],
                cwd=self.directory,
                stdin=subprocess.DEVNULL,
                stdout=self._log,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self._job.assign(self._process.pid)
            deadline = time.perf_counter() + self.connect_timeout
            while time.perf_counter() < deadline:
                if self._process.poll() is not None:
                    raise ConnectionError(
                        f"Private engine exited with code {self._process.returncode}. "
                        f"See {state / 'engine-output.log'}"
                    )
                candidate = LegacyWebSocketBackend(connect_timeout=0.25)
                try:
                    candidate.open()
                    remaining = deadline - time.perf_counter()
                    if remaining <= 0:
                        raise ConnectionError("Private engine connection exceeded startup deadline")
                    # The WebSocket starts before the camera and tracking model are ready.
                    # Keep the first frame so callers see real readiness without losing it.
                    first_frame = candidate.read(remaining)
                    if first_frame is None:
                        raise ConnectionError(
                            "Private engine connected but produced no camera frames within "
                            f"{self.connect_timeout:g}s. See {state / 'engine-output.log'}"
                        )
                    self._pending_frame = first_frame
                    self._backend = candidate
                    return
                except BaseException as exc:
                    candidate.close()
                    if not isinstance(exc, ConnectionError):
                        raise
                    time.sleep(0.05)
            raise ConnectionError(
                f"Private engine startup timed out. See {state / 'engine-output.log'}"
            )
        except BaseException:
            self.close()
            raise

    def read(self, timeout: float):
        if self._backend is None:
            raise RuntimeError("Managed tracking is not open")
        if self._process is not None and self._process.poll() is not None:
            raise ConnectionError(f"Private engine stopped with code {self._process.returncode}")
        if self._pending_frame is not None:
            frame, self._pending_frame = self._pending_frame, None
            return frame
        return self._backend.read(timeout)

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def release_tracking_client(self) -> None:
        """A coordinator owns the engine while applications own tracking clients."""
        if self._backend is not None:
            self._backend.close()
            self._backend = None
        self._pending_frame = None

    def close(self) -> None:
        try:
            if self._backend is not None:
                self._backend.close()
        finally:
            self._backend = None
            self._pending_frame = None
            try:
                if self._process is not None:
                    if self._process.poll() is None:
                        self._process.terminate()
                    try:
                        self._process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        self._process.kill()
                        self._process.wait(timeout=3)
            finally:
                self._process = None
                if self._job is not None:
                    self._job.close()
                    self._job = None
                if self._log is not None:
                    self._log.close()
                    self._log = None
