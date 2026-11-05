"""Private engine coordinator. Client sockets are leases; no permanent service."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import selectors
import socket
import time
from pathlib import Path

from ._locking import file_lock
from .backends.managed import ManagedLegacyBackend
from .delivery import _write_json


def serve(
    directory: Path, state: Path, *, startup_timeout=10, idle_timeout=1, backend_factory=None
):
    factory = backend_factory or ManagedLegacyBackend
    engine = factory(
        directory, connect_timeout=startup_timeout, reuse_existing=False, state_dir=state
    )
    token = secrets.token_hex(32)
    ready = state / "broker.json"
    selector = selectors.DefaultSelector()
    clients = {}
    state.mkdir(parents=True, exist_ok=True)
    try:
        engine.open()
        engine.release_tracking_client()
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            server.listen(16)
            server.setblocking(False)
            selector.register(server, selectors.EVENT_READ)
            _write_json(
                ready, {"pid": os.getpid(), "port": server.getsockname()[1], "token": token}
            )
            deadline = (
                time.perf_counter() + 5
            )  # The parent may die before obtaining its first lease.
            while True:
                active = any(client["authenticated"] for client in clients.values())
                if not active and not clients and time.perf_counter() >= deadline:
                    try:
                        with file_lock(state.parent / "engine.lock", timeout=0):
                            if not selector.select(timeout=0):
                                engine.close()
                                break
                    except TimeoutError:
                        continue
                for key, _events in selector.select(timeout=0.1):
                    connection = key.fileobj
                    if connection is server:
                        client, _address = server.accept()
                        client.setblocking(False)
                        selector.register(client, selectors.EVENT_READ)
                        clients[client] = {
                            "authenticated": False,
                            "buffer": b"",
                            "expires": time.perf_counter() + 2,
                        }
                        continue
                    entry = clients[connection]
                    try:
                        chunk = connection.recv(1024)
                        if not chunk:
                            raise OSError("Lease closed")
                        if entry["authenticated"]:
                            raise OSError("No messages are accepted after the lease handshake")
                        entry["buffer"] += chunk
                        if len(entry["buffer"]) > 1024:
                            raise OSError("Oversized lease handshake")
                        if b"\n" in entry["buffer"]:
                            request = json.loads(entry["buffer"])
                            if not secrets.compare_digest(str(request.get("token", "")), token):
                                raise OSError("Invalid lease token")
                            connection.sendall(b'{"ready":true}\n')
                            entry["authenticated"] = True
                    except (OSError, ValueError, AttributeError):
                        selector.unregister(connection)
                        connection.close()
                        del clients[connection]
                        deadline = time.perf_counter() + idle_timeout
                for connection, entry in list(clients.items()):
                    if not entry["authenticated"] and time.perf_counter() >= entry["expires"]:
                        selector.unregister(connection)
                        connection.close()
                        del clients[connection]
                if not engine.is_running:
                    raise RuntimeError("The private engine stopped")
    finally:
        for connection in clients:
            connection.close()
        selector.close()
        try:
            engine.close()
        finally:
            try:
                if json.loads(ready.read_text())["token"] == token:
                    ready.unlink()
            except (OSError, ValueError, KeyError):
                pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()
    serve(args.directory, args.state, startup_timeout=args.timeout)


if __name__ == "__main__":
    main()
