"""Strict, dependency-free teleoperation settings in SI units."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ._compat import tomllib
from .mapping import Mapping, _parse_rotation
from .models import Vector3


def _number(value: float, name: str, *, zero: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if value < 0 or (value == 0 and not zero):
        raise ValueError(f"{name} must be {'non-negative' if zero else 'positive'}")


@dataclass(frozen=True, slots=True)
class Workspace:
    minimum: Vector3
    maximum: Vector3

    def __post_init__(self) -> None:
        if any(a > b for a, b in zip(self.minimum, self.maximum, strict=True)):
            raise ValueError("Workspace minimum must not exceed maximum")

    def clamp(self, position: Vector3) -> Vector3:
        return Vector3(
            *(
                max(lo, min(hi, x))
                for x, lo, hi in zip(position, self.minimum, self.maximum, strict=True)
            )
        )

    def contains(self, position: Vector3) -> bool:
        return self.clamp(position) == position


@dataclass(frozen=True, slots=True)
class GripperMapping:
    source: Literal["grab", "pinch"] = "grab"
    open_value: float = 1.0
    closed_value: float = 0.0
    max_speed: float = 1.0
    deadband: float = 0.01

    def __post_init__(self) -> None:
        if self.source not in ("grab", "pinch"):
            raise ValueError("Gripper source must be 'grab' or 'pinch'")
        for name in ("open_value", "closed_value", "deadband"):
            value = getattr(self, name)
            _number(value, name, zero=True)
            if value > 1:
                raise ValueError(f"{name} must be in [0, 1]")
        _number(self.max_speed, "Gripper max_speed")

    def map(self, strength: float) -> float:
        return self.open_value + (self.closed_value - self.open_value) * strength


@dataclass(frozen=True, slots=True)
class TeleoperationConfig:
    workspace: Workspace
    max_linear_speed: float
    mapping: Mapping = Mapping()
    handedness: Literal["left", "right"] = "right"
    smoothing_time_constant: float = 0.05
    position_deadband: float = 0.001
    control_orientation: bool = False
    rotation_gain: float = 1.0
    max_angular_speed: float = 1.0
    gripper: GripperMapping | None = None
    max_frame_age: float = 0.1
    tracking_timeout: float = 0.15
    max_output_hz: float = 60.0

    def __post_init__(self) -> None:
        if self.handedness not in ("left", "right"):
            raise ValueError("Handedness must be 'left' or 'right'")
        if not isinstance(self.control_orientation, bool):
            raise ValueError("control_orientation must be true or false")
        for name in (
            "max_linear_speed",
            "max_angular_speed",
            "max_frame_age",
            "tracking_timeout",
            "max_output_hz",
        ):
            _number(getattr(self, name), name)
        for name in ("smoothing_time_constant", "position_deadband", "rotation_gain"):
            _number(getattr(self, name), name, zero=True)
        if self.max_output_hz > 1000:
            raise ValueError("max_output_hz must not exceed 1000")
        if self.max_frame_age > self.tracking_timeout:
            raise ValueError("max_frame_age must not exceed tracking_timeout")

    @classmethod
    def from_toml(cls, path: str | Path) -> TeleoperationConfig:
        with Path(path).open("rb") as stream:
            document = tomllib.load(stream)
        tables = {"mapping", "workspace", "teleoperation", "gripper"}
        if set(document) - tables:
            raise ValueError("Unknown configuration tables: " + ", ".join(set(document) - tables))
        if not {"workspace", "teleoperation"} <= set(document):
            raise ValueError("Configuration requires [workspace] and [teleoperation] tables")
        for name, table in document.items():
            if not isinstance(table, dict):
                raise ValueError(f"{name} must be a table")
        workspace = document["workspace"]
        if set(workspace) != {"minimum", "maximum"}:
            raise ValueError("Workspace requires exactly minimum and maximum")
        mapping = document.get("mapping", {})
        if set(mapping) - {"axes", "gain", "rotation"}:
            raise ValueError("Unknown mapping settings")
        axes = mapping.get("axes", ["x", "y", "z"])
        if not isinstance(axes, list) or any(not isinstance(axis, str) for axis in axes):
            raise ValueError("Mapping axes must be an array of axis names")
        rotation = _parse_rotation(mapping.get("rotation", [0, 0, 0, 1]))
        values = dict(document["teleoperation"])
        if "max_linear_speed" not in values:
            raise ValueError("teleoperation.max_linear_speed is required")
        allowed = set(cls.__dataclass_fields__) - {"workspace", "mapping", "gripper"}
        if set(values) - allowed:
            raise ValueError("Unknown teleoperation settings: " + ", ".join(set(values) - allowed))
        gripper = document.get("gripper")
        if gripper is not None and set(gripper) - set(GripperMapping.__dataclass_fields__):
            raise ValueError("Unknown gripper settings")
        return cls(
            workspace=Workspace(_vector(workspace["minimum"]), _vector(workspace["maximum"])),
            mapping=Mapping(tuple(axes), _vector(mapping.get("gain", [1, 1, 1])), rotation),
            gripper=None if gripper is None else GripperMapping(**gripper),
            **values,
        )


def _vector(values) -> Vector3:
    if not isinstance(values, list) or len(values) != 3:
        raise ValueError("Configuration vectors require three numbers")
    for value in values:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError("Configuration vectors require finite numbers")
    return Vector3(*values)
