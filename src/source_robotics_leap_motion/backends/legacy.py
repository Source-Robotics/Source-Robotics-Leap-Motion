"""Protocol-v6 JSON from the loopback WebSocket server in legacy Leap services.

This backend uses current Python, not the legacy LeapPython extension. It does
not install or replace the service. Unavailable bone rotations are reported as None.
"""

from __future__ import annotations

import json
import math
import time

from websocket import WebSocketException, WebSocketTimeoutException, create_connection

from ..errors import ConnectionError
from ..models import Bone, Finger, Frame, Hand, Palm, Quaternion, Vector3

URL = "ws://127.0.0.1:6437/v6.json"
FINGER_NAMES = ("thumb", "index", "middle", "ring", "pinky")


def _vector(data, scale: float = 1.0) -> Vector3:
    if not isinstance(data, list) or len(data) != 3:
        raise ValueError("Expected a three-component vector")
    if any(type(value) not in (int, float) for value in data):
        raise ValueError("Vector components must be numbers")
    return Vector3(*(value * scale for value in data))


def _cross(a: Vector3, b: Vector3) -> Vector3:
    return Vector3(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x)


def _unit(value: Vector3) -> Vector3:
    if value.norm < 1e-8:
        raise ValueError("Invalid hand direction or normal")
    return value * (1 / value.norm)


def palm_orientation(normal: Vector3, direction: Vector3) -> Quaternion:
    # Match LeapC palm basis: {normal x direction, -normal, -direction}.
    y = _unit(normal) * -1
    x = _unit(_cross(y, direction * -1))
    z = _unit(_cross(x, y))
    m = ((x.x, y.x, z.x), (x.y, y.y, z.y), (x.z, y.z, z.z))
    trace = m[0][0] + m[1][1] + m[2][2]
    if trace > 0:
        scale = math.sqrt(trace + 1) * 2
        values = (
            (m[2][1] - m[1][2]) / scale,
            (m[0][2] - m[2][0]) / scale,
            (m[1][0] - m[0][1]) / scale,
            scale / 4,
        )
    else:
        i = max(range(3), key=lambda index: m[index][index])
        j, k = (i + 1) % 3, (i + 2) % 3
        scale = math.sqrt(1 + m[i][i] - m[j][j] - m[k][k]) * 2
        q = [0.0] * 4
        q[i] = scale / 4
        q[j] = (m[j][i] + m[i][j]) / scale
        q[k] = (m[k][i] + m[i][k]) / scale
        q[3] = (m[k][j] - m[j][k]) / scale
        values = tuple(q)
    return Quaternion(*values)


def _finger(pointable: dict) -> Finger:
    kind = pointable["type"]
    if type(kind) is not int or not 0 <= kind < 5:
        raise ValueError("Invalid finger type")
    keys = ("carpPosition", "mcpPosition", "pipPosition", "dipPosition", "btipPosition")
    bones = ()
    if all(key in pointable for key in keys):
        joints = [_vector(pointable[key], 0.001) for key in keys]
        bones = tuple(
            Bone(start, end, pointable["width"] * 0.001, rotation=None)
            for start, end in zip(joints[:-1], joints[1:], strict=True)
        )
    return Finger(pointable["id"], FINGER_NAMES[kind], bones, bool(pointable["extended"]))


def decode_frame(data: dict) -> Frame:
    try:
        if type(data["id"]) is not int or type(data["timestamp"]) is not int:
            raise ValueError("Frame id and timestamp must be integers")
        hands = []
        if not isinstance(data["hands"], list) or len(data["hands"]) > 16:
            raise ValueError("Invalid hand array")
        for hand in data["hands"]:
            normal = _vector(hand["palmNormal"])
            direction = _vector(hand["direction"])
            fingers = tuple(
                _finger(pointable)
                for pointable in data.get("pointables", [])
                if pointable.get("handId") == hand["id"] and not pointable.get("tool", False)
            )
            arm = None
            if "elbow" in hand and "wrist" in hand:
                arm = Bone(
                    _vector(hand["elbow"], 0.001),
                    _vector(hand["wrist"], 0.001),
                    hand.get("armWidth", 0) * 0.001,
                    rotation=None,
                )
            hands.append(
                Hand(
                    id=hand["id"],
                    handedness=hand["type"],
                    palm=Palm(
                        position=_vector(hand["palmPosition"], 0.001),
                        orientation=palm_orientation(normal, direction),
                        velocity=_vector(hand["palmVelocity"], 0.001),
                        normal=normal,
                        direction=direction,
                        width=hand["palmWidth"] * 0.001,
                    ),
                    grab_strength=hand["grabStrength"],
                    pinch_strength=hand["pinchStrength"],
                    visible_time_us=round(hand.get("timeVisible", 0) * 1_000_000),
                    fingers=fingers,
                    arm=arm,
                )
            )
        return Frame(
            id=data["id"],
            timestamp_us=data["timestamp"],
            hands=tuple(hands),
            framerate=data.get("currentFrameRate", 0),
            clock_domain="leap_service",
        )
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as exc:
        raise ConnectionError(f"Invalid legacy tracking frame: {exc}") from exc


class LegacyWebSocketBackend:
    name = "legacy-websocket"

    def __init__(self, *, connect_timeout: float = 3.0):
        self.connect_timeout = connect_timeout
        self.service_version = None
        self._socket = None

    def open(self) -> None:
        try:
            self._socket = create_connection(
                URL,
                timeout=self.connect_timeout,
                origin="http://localhost",
                http_no_proxy=["127.0.0.1", "localhost"],
                # recv() still performs strict UTF-8 decoding in C. Avoid a second,
                # Python-level byte-validation pass over every local JSON message.
                skip_utf8_validation=True,
            )
            greeting = json.loads(self._socket.recv())
            if greeting.get("version") != 6:
                raise ConnectionError("Legacy tracking server did not negotiate JSON protocol v6")
            self.service_version = greeting.get("serviceVersion")
            self._socket.send(json.dumps({"focused": True}))
            self._socket.send(json.dumps({"background": True}))
        except (OSError, WebSocketException, ValueError, AttributeError) as exc:
            self.close()
            raise ConnectionError(
                f"Cannot connect to the local Leap WebSocket service: {exc}"
            ) from exc

    def read(self, timeout: float) -> Frame | None:
        if self._socket is None:
            raise RuntimeError("Legacy connection is not open")
        end = time.perf_counter() + timeout
        while (remaining := end - time.perf_counter()) > 0:
            self._socket.settimeout(min(remaining, 0.1))
            try:
                raw = self._socket.recv()
                if not raw:
                    raise ConnectionError("The local Leap WebSocket connection closed")
                if len(raw) > 2 * 1024 * 1024:
                    raise ConnectionError("Oversized legacy tracking message")
                data = json.loads(raw)
            except WebSocketTimeoutException:
                continue
            except (OSError, WebSocketException, ValueError) as exc:
                raise ConnectionError(f"Legacy tracking connection failed: {exc}") from exc
            if not isinstance(data, dict):
                raise ConnectionError("Invalid legacy tracking message")
            if "hands" in data:
                return decode_frame(data)
            event = data.get("event", {})
            if (
                event.get("type") == "deviceEvent"
                and event.get("state", {}).get("attached") is False
            ):
                raise ConnectionError("The Leap camera was unplugged")
        return None

    def close(self) -> None:
        if self._socket is not None:
            socket, self._socket = self._socket, None
            socket.close(timeout=0.2)
