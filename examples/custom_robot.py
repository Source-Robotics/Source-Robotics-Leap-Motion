"""Runnable callback integration using a simulated controller.

Replace the adapter callbacks with your controller's SDK calls. Convert SI units
at that boundary, implement a real hold/cancel operation, and enforce command expiry
in the robot controller. The built-in example never connects to a physical robot.
"""

import argparse
import time
from pathlib import Path

from source_robotics_leap_motion import Pose, TeleoperationConfig, Teleoperator, Tracker
from source_robotics_leap_motion.adapters import CallbackAdapter, SimulatedArm


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="synthetic hand instead of camera")
    parser.add_argument("--duration", type=float, default=10)
    args = parser.parse_args()
    config = TeleoperationConfig.from_toml(Path(__file__).with_name("teleoperation.toml"))
    center = (config.workspace.minimum + config.workspace.maximum) * 0.5
    controller = SimulatedArm(Pose(center))
    robot = CallbackAdapter(
        send=controller.send,
        hold=controller.hold,
        feedback=controller.read_feedback,
        open=controller.open,
        close=controller.close,
        orientation=True,
        gripper=True,
    )
    factory = Tracker.demo if args.demo else Tracker
    with factory(mode="latest", max_frame_age=config.max_frame_age) as tracker:
        with Teleoperator(tracker, robot=robot, config=config) as teleop:
            teleop.arm()  # Explicit calibration using fresh hand data and robot feedback.
            started = time.monotonic()
            while time.monotonic() - started < args.duration:
                target = teleop.step()
                if target is not None:
                    print(target.position)
                if teleop.status.state == "tracking_lost":
                    print("Output held:", teleop.status.reason)
                    break  # Deliberate rearming is required after loss.


if __name__ == "__main__":
    main()
