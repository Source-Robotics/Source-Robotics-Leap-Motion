"""Robot integration contracts; imports never connect to a controller."""

from .base import RobotAdapter
from .callback import CallbackAdapter
from .simulated import SimulatedArm

__all__ = ["CallbackAdapter", "RobotAdapter", "SimulatedArm"]
