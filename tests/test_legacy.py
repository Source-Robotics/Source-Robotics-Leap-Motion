import json

import pytest

from source_robotics_leap_motion import ConnectionError, Quaternion, Vector3
from source_robotics_leap_motion.backends.auto import AutoBackend
from source_robotics_leap_motion.backends.legacy import (
    LegacyWebSocketBackend,
    decode_frame,
    palm_orientation,
)
from source_robotics_leap_motion.errors import RuntimeNotFoundError


@pytest.fixture
def legacy_frame():
    return {
        "id": 100,
        "timestamp": 123456,
        "currentFrameRate": 115.0,
        "hands": [
            {
                "id": 7,
                "type": "right",
                "palmNormal": [0, -1, 0],
                "direction": [0, 0, -1],
                "palmPosition": [125, 250, -75],
                "palmVelocity": [1000, 0, 0],
                "palmWidth": 80,
                "grabStrength": 0.8,
                "pinchStrength": 0.2,
                "timeVisible": 2,
                "elbow": [125, 100, 150],
                "wrist": [125, 200, 0],
                "armWidth": 50,
            }
        ],
        "pointables": [
            {
                "id": 12,
                "handId": 7,
                "type": 1,
                "extended": True,
                "width": 15,
                "carpPosition": [0, 1, 2],
                "mcpPosition": [0, 2, 2],
                "pipPosition": [0, 3, 2],
                "dipPosition": [0, 4, 2],
                "btipPosition": [0, 5, 2],
            }
        ],
    }


def test_legacy_frame_converts_units_and_preserves_missing_rotation(legacy_frame):
    frame = decode_frame(legacy_frame)
    hand = frame.right_hand
    assert hand.palm.position == Vector3(0.125, 0.25, -0.075)
    assert hand.palm.velocity.x == 1
    assert hand.palm.orientation == Quaternion()
    assert hand.visible_time_us == 2_000_000
    assert hand.pinch_distance is None
    assert len(hand.fingers[0].bones) == 4
    assert hand.fingers[0].bones[-1].next_joint.y == 0.005
    assert hand.fingers[0].bones[-1].rotation is None


@pytest.mark.parametrize(
    "normal,direction,expected",
    [
        (Vector3(0, 1, 0), Vector3(0, 0, 1), Quaternion(1, 0, 0, 0)),
        (Vector3(0, -1, 0), Vector3(0, 0, 1), Quaternion(0, 1, 0, 0)),
        (Vector3(0, 1, 0), Vector3(0, 0, -1), Quaternion(0, 0, 1, 0)),
    ],
)
def test_palm_orientation_handles_180_degree_rotations(normal, direction, expected):
    assert palm_orientation(normal, direction) == expected


def test_legacy_empty_frame_is_valid():
    assert decode_frame({"id": 0, "timestamp": 0, "hands": []}).hands == ()


def test_legacy_invalid_normal_is_rejected(legacy_frame):
    legacy_frame["hands"][0]["palmNormal"] = [0, 0, 0]
    with pytest.raises(ConnectionError):
        decode_frame(legacy_frame)


def test_legacy_connection_reads_greeting_then_frames(monkeypatch, legacy_frame):
    from source_robotics_leap_motion.backends import legacy

    class Socket:
        def __init__(self):
            self.messages = iter(
                [
                    json.dumps({"version": 6, "serviceVersion": "3.2.1+45911"}),
                    json.dumps(legacy_frame),
                ]
            )
            self.closed = False

        def recv(self):
            return next(self.messages)

        def send(self, message):
            assert set(json.loads(message)) <= {"focused", "background"}

        def settimeout(self, timeout):
            assert 0 < timeout <= 0.1

        def close(self, timeout):
            self.closed = True

    socket = Socket()
    monkeypatch.setattr(legacy, "create_connection", lambda *args, **kwargs: socket)
    backend = LegacyWebSocketBackend()
    backend.open()
    assert backend.service_version == "3.2.1+45911"
    assert backend.read(1).right_hand.id == 7
    backend.close()
    assert socket.closed


def test_auto_falls_back_without_requiring_old_python(monkeypatch):
    from source_robotics_leap_motion.backends import auto

    class Native:
        def __init__(self, **kwargs):
            pass

        def open(self):
            raise RuntimeNotFoundError("No native client")

        def close(self):
            pass

    class Legacy(Native):
        name = "legacy-websocket"

        def open(self):
            pass

        def read(self, timeout):
            return decode_frame({"id": 0, "timestamp": 0, "hands": []})

    monkeypatch.setattr(auto, "LeapCBackend", Native)
    monkeypatch.setattr(auto, "LegacyWebSocketBackend", Legacy)
    backend = AutoBackend()
    backend.open()
    assert backend.name == "legacy-websocket"
    assert backend.read(1).hands == ()
    backend.close()


def test_auto_starts_cached_runtime_when_no_service_is_available(monkeypatch, tmp_path):
    from unittest.mock import Mock

    from source_robotics_leap_motion.backends import auto, shared

    failed = Mock()
    failed.open.side_effect = ConnectionError("No installed service")
    monkeypatch.setattr(auto, "LeapCBackend", Mock(return_value=failed))
    monkeypatch.setattr(auto, "LegacyWebSocketBackend", Mock(return_value=failed))
    monkeypatch.setattr(auto, "ensure_runtime", lambda: tmp_path)
    managed = Mock(name="private runtime")
    managed.name = "managed-legacy"
    managed.details = {"mode": "shared-private"}
    managed.read.return_value = decode_frame({"id": 7, "timestamp": 1, "hands": []})
    monkeypatch.setattr(shared, "SharedRuntimeBackend", Mock(return_value=managed))
    backend = AutoBackend()
    backend.open()
    assert backend.details == {"mode": "shared-private"}
    assert backend.read(1).id == 7
    backend.close()
    managed.close.assert_called_once()


def test_auto_acquires_private_lease_instead_of_using_unleased_websocket(monkeypatch, tmp_path):
    from unittest.mock import Mock

    from source_robotics_leap_motion.backends import auto, shared

    native = Mock()
    native.open.side_effect = RuntimeNotFoundError("No native library")
    monkeypatch.setattr(auto, "LeapCBackend", Mock(return_value=native))
    monkeypatch.setattr(auto, "cached_runtime", lambda: tmp_path)
    legacy = Mock()
    monkeypatch.setattr(auto, "LegacyWebSocketBackend", legacy)
    private = Mock()
    private.name = "managed-legacy"
    monkeypatch.setattr(shared, "SharedRuntimeBackend", Mock(return_value=private))
    backend = AutoBackend()
    backend.open()
    legacy.assert_not_called()
    private.open.assert_called_once()
    backend.close()
