"""Select installed LeapC first, with a local legacy-service fallback."""

from ..delivery import cached_runtime, ensure_runtime
from ..errors import ConnectionError, RuntimeNotFoundError
from .leapc import LeapCBackend
from .legacy import LegacyWebSocketBackend


class AutoBackend:
    name = "auto"

    def __init__(self, *, connect_timeout: float = 5.0):
        self.connect_timeout = connect_timeout
        self._selected = None

    def open(self) -> None:
        native = LeapCBackend(connect_timeout=self.connect_timeout)
        try:
            native.open()
            self._selected = native
        except (RuntimeNotFoundError, ConnectionError) as native_error:
            native.close()
            # A cached runtime may already be owned by our coordinator. Acquire a
            # lease before opening its WebSocket; an unleased client would otherwise
            # lose tracking when another application releases the last real lease.
            try:
                directory = cached_runtime()
            except RuntimeNotFoundError:
                directory = None
            if directory is not None:
                from .shared import SharedRuntimeBackend

                managed = SharedRuntimeBackend(directory, connect_timeout=self.connect_timeout)
                try:
                    managed.open()
                    self._selected = managed
                    self.name = managed.name
                    return
                except (RuntimeNotFoundError, ConnectionError):
                    managed.close()
            legacy = LegacyWebSocketBackend(connect_timeout=self.connect_timeout)
            try:
                legacy.open()
                self._selected = legacy
            except ConnectionError as legacy_error:
                legacy.close()
                from .shared import SharedRuntimeBackend

                try:
                    directory = ensure_runtime()
                    managed = SharedRuntimeBackend(directory, connect_timeout=self.connect_timeout)
                    try:
                        managed.open()
                    except BaseException:
                        managed.close()
                        raise
                    self._selected = managed
                except (RuntimeNotFoundError, ConnectionError) as setup_error:
                    raise RuntimeNotFoundError(
                        f"No usable tracking backend.\nLeapC: {native_error}\n"
                        f"Legacy service: {legacy_error}\nSetup: {setup_error}"
                    ) from setup_error
        self.name = self._selected.name

    @property
    def details(self):
        return getattr(self._selected, "details", None)

    def read(self, timeout: float):
        if self._selected is None:
            raise RuntimeError("Tracking backend is not open")
        return self._selected.read(timeout)

    def close(self) -> None:
        if self._selected is not None:
            self._selected.close()
            self._selected = None
