"""A simulated Cartesian receiver with its own interpolation/expiry worker."""

from __future__ import annotations

import threading
import time

from ..control_config import _number
from ..control_models import Pose, PoseTarget, RobotCapabilities, RobotFeedback
from ..errors import AdapterError
from ..receiver import CartesianReceiver, ReceiverConfig, ReceiverStatus


class SimulatedReceiver:
    """No physical dynamics, network transport, or robot connection.

    Open starts one worker; close wakes and joins it. The worker advances bounded
    interpolation and freezes at command expiry even while the sender is idle.
    """

    capabilities = RobotCapabilities(
        orientation=True, gripper=True, feedback=True, command_sessions=True
    )

    def __init__(
        self,
        initial_pose: Pose,
        *,
        config: ReceiverConfig,
        gripper: float = 1.0,
        update_hz: float = 200.0,
    ) -> None:
        _number(update_hz, "Receiver update_hz")
        if update_hz > 1000:
            raise ValueError("Receiver update_hz must not exceed 1000")
        self.config, self.update_hz = config, update_hz
        self._receiver = CartesianReceiver(RobotFeedback(initial_pose, gripper), config=config)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._opened = False
        self._error: Exception | None = None
        self.last_target: PoseTarget | None = None
        self.targets_sent = 0

    def _require_open(self) -> None:
        if not self._opened:
            raise AdapterError("Open the simulated receiver first")

    def _check_worker(self) -> None:
        if self._error is not None:
            raise AdapterError("Simulated receiver worker failed") from self._error

    @property
    def worker_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def receiver_status(self) -> ReceiverStatus:
        with self._lock:
            if self._opened and self._error is None:
                self._receiver.advance()
            return self._receiver.status

    @property
    def hold_reason(self) -> str:
        status = self.receiver_status
        return "" if status.state == "active" else status.reason

    def open(self) -> None:
        with self._lock:
            if self._opened or self.worker_alive:
                raise AdapterError("Simulated receiver is already open")
            self._receiver = CartesianReceiver(self._receiver.feedback, config=self.config)
            self._error = None
            self._stop = threading.Event()
            self._opened = True
            self._thread = threading.Thread(
                target=self._run, name="source-leap-receiver", daemon=True
            )
            try:
                self._thread.start()
            except BaseException:
                self._opened = False
                self._stop.set()
                self._receiver.close()
                raise

    def begin_session(self, session_id: str) -> None:
        with self._lock:
            self._require_open()
            self._check_worker()
            self._receiver.begin_session(session_id)

    def read_feedback(self) -> RobotFeedback:
        with self._lock:
            self._require_open()
            self._check_worker()
            return self._receiver.advance()

    def send(self, target: PoseTarget) -> None:
        with self._lock:
            self._require_open()
            self._check_worker()
            if not self._receiver.accept(target):
                status = self._receiver.status
                raise AdapterError(
                    f"Receiver rejected command: {status.last_rejection} ({status.reason})"
                )
            self.last_target = target
            self.targets_sent += 1

    def hold(self, reason: str) -> None:
        with self._lock:
            self._require_open()
            self._receiver.hold(reason)

    def close(self) -> None:
        thread = None
        try:
            with self._lock:
                thread = self._thread
                self._stop.set()
                self._opened = False
                self._receiver.close()
        finally:
            if thread is not None and thread is not threading.current_thread():
                thread.join(timeout=1.0)
                if thread.is_alive():
                    raise AdapterError("Simulated receiver worker did not close")

    def _run(self) -> None:
        period = 1.0 / self.update_hz
        deadline = time.monotonic()
        while not self._stop.is_set():
            try:
                with self._lock:
                    if not self._opened:
                        return
                    self._receiver.advance()
            except Exception as error:
                with self._lock:
                    if not self._opened:
                        return
                    self._error = error
                    self._receiver.fault("receiver_worker_failed")
                self._stop.set()
                return
            deadline += period
            now = time.monotonic()
            if deadline <= now:
                deadline = now + period  # Skip missed ticks rather than catching up in a burst.
            self._stop.wait(max(0.0, deadline - now))
