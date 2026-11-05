"""Versioned JSON Lines recordings with owned SI-unit frames."""

from __future__ import annotations

import json
import math
from collections.abc import Iterator
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from ._compat import Self
from .errors import RecordingError
from .models import Bone, Finger, Frame, Hand, Palm, Quaternion, Vector3

SCHEMA = "source-robotics-leap-motion/recording"
SCHEMA_VERSION = 1
MAX_LINE_BYTES = 2 * 1024 * 1024


def frame_to_dict(frame: Frame) -> dict:
    return asdict(frame)


def _integer(value) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("Expected a non-negative integer")
    return value


def _number(value) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("Expected a finite number")
    return float(value)


def _vector(data: dict) -> Vector3:
    return Vector3(*(_number(data[axis]) for axis in ("x", "y", "z")))


def _quaternion(data: dict) -> Quaternion:
    return Quaternion(*(_number(data[axis]) for axis in ("x", "y", "z", "w")))


def _bone(data: dict) -> Bone:
    return Bone(
        _vector(data["previous_joint"]),
        _vector(data["next_joint"]),
        _number(data["width"]),
        _quaternion(data["rotation"]) if data["rotation"] is not None else None,
    )


def frame_from_dict(data: dict) -> Frame:
    """Decode a frame strictly enough to reject corrupt or non-finite input."""
    try:
        hands = []
        if not isinstance(data["hands"], list) or len(data["hands"]) > 16:
            raise ValueError("Invalid hand list")
        for hand in data["hands"]:
            palm = hand["palm"]
            fingers = []
            for finger in hand["fingers"]:
                if finger["name"] not in ("thumb", "index", "middle", "ring", "pinky"):
                    raise ValueError("Invalid finger name")
                if type(finger["extended"]) is not bool:
                    raise ValueError("Expected boolean finger extension")
                fingers.append(
                    Finger(
                        _integer(finger["id"]),
                        finger["name"],
                        tuple(_bone(bone) for bone in finger["bones"]),
                        finger["extended"],
                    )
                )
            hands.append(
                Hand(
                    id=_integer(hand["id"]),
                    handedness=hand["handedness"],
                    palm=Palm(
                        _vector(palm["position"]),
                        _quaternion(palm["orientation"]),
                        _vector(palm["velocity"]),
                        _vector(palm["normal"]),
                        _vector(palm["direction"]),
                        _number(palm["width"]),
                    ),
                    grab_strength=_number(hand["grab_strength"]),
                    pinch_strength=_number(hand["pinch_strength"]),
                    pinch_distance=(
                        _number(hand["pinch_distance"])
                        if hand["pinch_distance"] is not None
                        else None
                    ),
                    visible_time_us=_integer(hand["visible_time_us"]),
                    fingers=tuple(fingers),
                    arm=_bone(hand["arm"]) if hand["arm"] else None,
                )
            )
        if not isinstance(data["clock_domain"], str) or not data["clock_domain"]:
            raise ValueError("Missing timestamp clock domain")
        return Frame(
            id=_integer(data["id"]),
            timestamp_us=_integer(data["timestamp_us"]),
            hands=tuple(hands),
            framerate=_number(data["framerate"]),
            device_id=_integer(data["device_id"]),
            clock_domain=data["clock_domain"],
        )
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise RecordingError(f"Invalid frame: {exc}") from exc


class Recorder:
    """Write one session. Existing recordings are protected unless overwrite=True."""

    def __init__(self, path: str | Path, *, overwrite: bool = False) -> None:
        self.path = Path(path)
        self.overwrite = overwrite
        self._file = None

    def __enter__(self) -> Self:
        if self._file is not None:
            raise RuntimeError("Recorder is already open")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("w" if self.overwrite else "x", encoding="utf-8")
        metadata = {
            "schema": SCHEMA,
            "version": SCHEMA_VERSION,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "units": "metres",
            "coordinate_frame": "leap_camera",
            "quaternion_order": "xyzw",
        }
        try:
            self._file.write(json.dumps(metadata) + "\n")
        except BaseException:
            self._file.close()
            self._file = None
            raise
        return self

    def write(self, frame: Frame) -> None:
        if self._file is None:
            raise RuntimeError("Open Recorder in a with block first")
        line = json.dumps({"frame": frame_to_dict(frame)}, allow_nan=False, separators=(",", ":"))
        if len(line.encode("utf-8")) > MAX_LINE_BYTES:
            raise RecordingError("Frame is too large for the recording format")
        self._file.write(line + "\n")

    def __exit__(self, *_exc) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None


def _json_line(stream, line_number: int) -> dict | None:
    line = stream.readline(MAX_LINE_BYTES + 1)
    if not line:
        return None
    if len(line) > MAX_LINE_BYTES:
        raise RecordingError(f"Line {line_number} exceeds the recording size limit")
    try:
        result = json.loads(line)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise RecordingError(f"Invalid JSON on line {line_number}: {exc}") from exc
    if not isinstance(result, dict):
        raise RecordingError(f"Expected a JSON object on line {line_number}")
    return result


def read_recording(path: str | Path) -> Iterator[Frame]:
    """Stream recordings; memory does not grow with session length."""
    with Path(path).open("rb") as stream:
        metadata = _json_line(stream, 1)
        if metadata is None or metadata.get("schema") != SCHEMA:
            raise RecordingError("Not a source-robotics-leap-motion recording")
        if metadata.get("version") != SCHEMA_VERSION:
            raise RecordingError(f"Unsupported recording version: {metadata.get('version')}")
        if (
            metadata.get("units") != "metres"
            or metadata.get("coordinate_frame") != "leap_camera"
            or metadata.get("quaternion_order") != "xyzw"
        ):
            raise RecordingError("Unsupported recording units or coordinate conventions")
        line_number = 2
        while (record := _json_line(stream, line_number)) is not None:
            try:
                yield frame_from_dict(record["frame"])
            except (KeyError, RecordingError) as exc:
                raise RecordingError(f"Invalid frame on line {line_number}: {exc}") from exc
            line_number += 1
