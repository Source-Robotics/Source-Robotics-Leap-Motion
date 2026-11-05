"""Print mapped positions. This example does not connect to or move a robot."""

from pathlib import Path

from source_robotics_leap_motion import Mapping, Tracker, Vector3

mapping = Mapping.from_toml(Path(__file__).with_name("my_arm.toml"))

with Tracker.demo(realtime=False) as tracker:
    first = tracker.read().right_hand
    # In a real integration, get this reference from the robot's own feedback.
    example_robot_origin = Vector3(0.2, 0, 0.2)
    for _ in range(10):
        hand = tracker.read().right_hand
        target = mapping.map_position(
            hand.palm.position,
            hand_origin=first.palm.position,
            robot_origin=example_robot_origin,
        )
        print(target)
