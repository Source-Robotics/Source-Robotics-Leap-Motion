import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from source_robotics_leap_motion import setup
from source_robotics_leap_motion.backends import leapc
from source_robotics_leap_motion.backends._native import NativeMessage
from source_robotics_leap_motion.errors import RuntimeNotFoundError


@pytest.mark.parametrize(
    "devices,expected",
    [
        ([], "not-connected"),
        ([{"name": "Leap", "problem_code": 0}], "present"),
        ([{"name": "Leap", "problem_code": 28}], "driver-required"),
        ([{"name": "Leap", "problem_code": 43}], "device-error"),
    ],
)
def test_driver_detection_distinguishes_missing_driver_from_absent_camera(
    monkeypatch, devices, expected
):
    monkeypatch.setattr(setup.sys, "platform", "win32")
    monkeypatch.setattr(setup.subprocess, "CREATE_NO_WINDOW", 0, raising=False)
    monkeypatch.setattr(
        setup.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(devices),
        ),
    )
    assert setup.device_status()["status"] == expected


def test_driver_inspection_denied_is_not_a_missing_driver(monkeypatch):
    monkeypatch.setattr(setup.sys, "platform", "win32")
    monkeypatch.setattr(setup.subprocess, "CREATE_NO_WINDOW", 0, raising=False)
    monkeypatch.setattr(setup.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1))
    assert setup.device_status()["status"] == "unknown"


def test_driver_install_does_not_replace_a_working_driver(monkeypatch, tmp_path):
    monkeypatch.setattr(setup.sys, "platform", "win32")
    monkeypatch.setattr(setup, "inspect_runtime", lambda path: {})
    monkeypatch.setattr(setup, "device_status", lambda: {"status": "present"})
    with pytest.raises(RuntimeNotFoundError, match="Existing working drivers"):
        setup.install_windows_driver(tmp_path)


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_posix_native_backend_uses_cdecl_loader(monkeypatch, tmp_path, platform):
    import ctypes as C

    library = Mock()
    library.LeapCreateConnection.side_effect = lambda config, handle: (
        setattr(C.cast(handle, C.POINTER(C.c_void_p)).contents, "value", 123) or 0
    )
    library.LeapOpenConnection.return_value = 0
    library.LeapSetPolicyFlags.return_value = 0

    def poll(handle, timeout, message):
        C.cast(message, C.POINTER(NativeMessage)).contents.type = leapc.CONNECTION
        return 0

    library.LeapPollConnection.side_effect = poll
    loader = Mock(return_value=library)
    monkeypatch.setattr(leapc.sys, "platform", platform)
    monkeypatch.setattr(leapc, "find_library", lambda selected: tmp_path / "libLeapC.so")
    monkeypatch.setattr(leapc.C, "CDLL", loader)
    native = leapc.LeapCBackend()
    native.open()
    loader.assert_called_once()
    library.LeapSetPolicyFlags.assert_called_once_with(native._handle, 1, 0)
    native.close()
    library.LeapCloseConnection.assert_called_once()
    library.LeapDestroyConnection.assert_called_once()
