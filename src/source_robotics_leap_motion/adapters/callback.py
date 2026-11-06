"""Integrate an existing controller through explicit target and hold callbacks."""

from collections.abc import Callable

from ..control_models import PoseTarget, RobotCapabilities, RobotFeedback
from ..errors import AdapterError


class CallbackAdapter:
    def __init__(
        self,
        send: Callable[[PoseTarget], None],
        *,
        hold: Callable[[str], None],
        feedback: Callable[[], RobotFeedback] | None = None,
        open: Callable[[], None] | None = None,
        close: Callable[[], None] | None = None,
        orientation: bool = False,
        gripper: bool = False,
        begin_session: Callable[[str], None] | None = None,
    ) -> None:
        self.capabilities = RobotCapabilities(
            orientation=orientation,
            gripper=gripper,
            feedback=feedback is not None,
            command_sessions=begin_session is not None,
        )
        self._send, self._hold, self._feedback = send, hold, feedback
        self._open, self._close = open, close
        self._begin_session = begin_session
        self._opened = False

    def open(self) -> None:
        if self._opened:
            raise AdapterError("Callback adapter is already open")
        # Mark the attempt so close can release a partially opened controller.
        self._opened = True
        if self._open is not None:
            self._open()

    def read_feedback(self) -> RobotFeedback | None:
        self._require_open()
        return None if self._feedback is None else self._feedback()

    def begin_session(self, session_id: str) -> None:
        self._require_open()
        if self._begin_session is not None:
            self._begin_session(session_id)

    def send(self, target: PoseTarget) -> None:
        self._require_open()
        if target.orientation is not None and not self.capabilities.orientation:
            raise AdapterError("Adapter does not support orientation commands")
        if target.gripper is not None and not self.capabilities.gripper:
            raise AdapterError("Adapter does not support gripper commands")
        self._send(target)

    def hold(self, reason: str) -> None:
        self._require_open()
        self._hold(reason)

    def close(self) -> None:
        if self._opened:
            self._opened = False
            if self._close is not None:
                self._close()

    def _require_open(self) -> None:
        if not self._opened:
            raise AdapterError("Open the callback adapter first")
