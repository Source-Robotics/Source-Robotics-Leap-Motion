"""Pure coordinate mapping primitives; no network or robot side effects."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from ._compat import tomllib
from .models import Vector3

ZERO = Vector3()


@dataclass(frozen=True, slots=True)
class Mapping:
    """Map metre positions into an arm's frame using a proper rotation and gains.

    target = robot_origin + gain * rotation * (hand_position - hand_origin)
    Defaults are identity; no robot-specific bounds or home pose are assumed.
    """

    axes: tuple[str, str, str] = ("x", "y", "z")
    gain: Vector3 = Vector3(1, 1, 1)

    def __post_init__(self) -> None:
        if len(self.axes) != 3 or {axis.lstrip("-") for axis in self.axes} != {"x", "y", "z"}:
            raise ValueError("Axes must be a signed permutation of x, y, z")
        if any(axis not in ("x", "y", "z", "-x", "-y", "-z") for axis in self.axes):
            raise ValueError("Axis names must be x, y, z, -x, -y, or -z")
        order = ["xyz".index(axis.lstrip("-")) for axis in self.axes]
        inversions = sum(order[i] > order[j] for i in range(3) for j in range(i + 1, 3))
        negatives = sum(axis.startswith("-") for axis in self.axes)
        if (inversions + negatives) % 2:
            raise ValueError("Axis mapping must preserve handedness (a rotation, not a reflection)")
        if any(not math.isfinite(value) or value < 0 for value in self.gain):
            raise ValueError("Gains must be finite and non-negative; use zero to lock an axis")

    def map_position(
        self,
        position: Vector3,
        *,
        hand_origin: Vector3 = ZERO,
        robot_origin: Vector3 = ZERO,
    ) -> Vector3:
        delta = position - hand_origin
        rotated = [
            getattr(delta, axis.lstrip("-")) * (-1 if axis.startswith("-") else 1)
            for axis in self.axes
        ]
        return robot_origin + Vector3(
            *(component * gain for component, gain in zip(rotated, self.gain, strict=True))
        )

    @classmethod
    def from_toml(cls, path: str | Path) -> Mapping:
        with Path(path).open("rb") as stream:
            document = tomllib.load(stream)
        if set(document) != {"mapping"}:
            raise ValueError("Configuration must contain one [mapping] table")
        config = document["mapping"]
        unknown = set(config) - {"axes", "gain"}
        if unknown:
            raise ValueError(f"Unknown mapping settings: {', '.join(sorted(unknown))}")
        gain = config.get("gain", [1.0, 1.0, 1.0])
        if len(gain) != 3:
            raise ValueError("Gain must have three values")
        return cls(tuple(config.get("axes", ("x", "y", "z"))), Vector3(*gain))
