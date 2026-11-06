"""Robot integration contracts; imports never connect to a controller."""

from .base import RobotAdapter, SessionRobotAdapter
from .callback import CallbackAdapter
from .receiver import SimulatedReceiver
from .simulated import SimulatedArm

__all__ = [
    "CallbackAdapter",
    "RobotAdapter",
    "SessionRobotAdapter",
    "SimulatedArm",
    "SimulatedReceiver",
]
