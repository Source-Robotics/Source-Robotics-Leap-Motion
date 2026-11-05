import threading
import time

from source_robotics_leap_motion._broker import serve
from source_robotics_leap_motion.backends.shared import _lease


def test_two_clients_keep_engine_alive_until_last_lease_closes(tmp_path):
    class Engine:
        is_running = True
        closed = threading.Event()

        def __init__(self, *args, **kwargs):
            pass

        def open(self):
            pass

        def release_tracking_client(self):
            pass

        def close(self):
            self.is_running = False
            self.closed.set()

    state = tmp_path / "engine"
    errors = []

    def worker():
        try:
            serve(tmp_path, state, idle_timeout=0.05, backend_factory=Engine)
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    first = second = None
    try:
        deadline = time.perf_counter() + 3
        while first is None and time.perf_counter() < deadline:
            first = _lease(state)
            if first is None:
                time.sleep(0.02)
        assert first is not None
        second = _lease(state)
        assert second is not None
        first.close()
        first = None
        assert not Engine.closed.wait(timeout=0.2)
        second.close()
        second = None
        thread.join(timeout=3)
        assert not thread.is_alive()
        assert Engine.closed.is_set()
        assert not (state / "broker.json").exists()
        assert not errors
    finally:
        if first is not None:
            first.close()
        if second is not None:
            second.close()
        thread.join(timeout=3)
