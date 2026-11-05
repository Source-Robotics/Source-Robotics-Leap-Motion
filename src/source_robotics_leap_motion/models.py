"""Owned, immutable tracking data. Distances are metres; timestamps are microseconds."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class Vector3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __post_init__(self) -> None:
        if not all(math.isfinite(v) for v in self):
            raise ValueError("Vector coordinates must be finite")

    def __iter__(self):
        return iter((self.x, self.y, self.z))

    def __add__(self, other: Vector3) -> Vector3:
        return Vector3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Vector3) -> Vector3:
        return Vector3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scale: float) -> Vector3:
        return Vector3(self.x * scale, self.y * scale, self.z * scale)

    @property
    def norm(self) -> float:
        return math.sqrt(self.x**2 + self.y**2 + self.z**2)


@dataclass(frozen=True, slots=True)
class Quaternion:
    """Rotation with named x/y/z/w components. Identity is (0, 0, 0, 1)."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    w: float = 1.0

    def __post_init__(self) -> None:
        values = (self.x, self.y, self.z, self.w)
        if not all(math.isfinite(v) for v in values):
            raise ValueError("Quaternion components must be finite")
        if not math.isclose(sum(v * v for v in values), 1.0, abs_tol=1e-3):
            raise ValueError("Quaternion must have unit length")


@dataclass(frozen=True, slots=True)
class Palm:
    position: Vector3
    orientation: Quaternion = Quaternion()
    velocity: Vector3 = Vector3()
    normal: Vector3 = Vector3(0.0, -1.0, 0.0)
    direction: Vector3 = Vector3(0.0, 0.0, -1.0)
    width: float = 0.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.width) or self.width < 0:
            raise ValueError("Palm width must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class Bone:
    previous_joint: Vector3
    next_joint: Vector3
    width: float
    rotation: Quaternion | None

    def __post_init__(self) -> None:
        if not math.isfinite(self.width) or self.width < 0:
            raise ValueError("Bone width must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class Finger:
    id: int
    name: Literal["thumb", "index", "middle", "ring", "pinky"]
    bones: tuple[Bone, ...]
    extended: bool


@dataclass(frozen=True, slots=True)
class Hand:
    id: int
    handedness: Literal["left", "right"]
    palm: Palm
    grab_strength: float = 0.0
    pinch_strength: float = 0.0
    pinch_distance: float | None = None
    visible_time_us: int = 0
    fingers: tuple[Finger, ...] = ()
    arm: Bone | None = None

    def __post_init__(self) -> None:
        if self.handedness not in ("left", "right"):
            raise ValueError("Handedness must be 'left' or 'right'")
        if not all(0 <= strength <= 1 for strength in (self.grab_strength, self.pinch_strength)):
            raise ValueError("Grab and pinch strengths must be between 0 and 1")
        if self.pinch_distance is not None and (
            not math.isfinite(self.pinch_distance) or self.pinch_distance < 0
        ):
            raise ValueError("Pinch distance must be finite and non-negative")
        if self.visible_time_us < 0:
            raise ValueError("Visible time must be non-negative")


@dataclass(frozen=True, slots=True)
class Frame:
    id: int
    timestamp_us: int
    hands: tuple[Hand, ...] = ()
    framerate: float = 0.0
    device_id: int = 0
    clock_domain: str = "leap_service"

    def __post_init__(self) -> None:
        if self.timestamp_us < 0:
            raise ValueError("Frame timestamp must be non-negative")
        if not math.isfinite(self.framerate) or self.framerate < 0:
            raise ValueError("Frame rate must be finite and non-negative")

    @property
    def right_hand(self) -> Hand | None:
        return next((hand for hand in self.hands if hand.handedness == "right"), None)

    @property
    def left_hand(self) -> Hand | None:
        return next((hand for hand in self.hands if hand.handedness == "left"), None)
