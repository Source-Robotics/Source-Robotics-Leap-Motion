"""Show receiver-side expiry with a deterministic clock and no hardware or threads."""

from source_robotics_leap_motion import (
    CartesianReceiver,
    Pose,
    PoseTarget,
    ReceiverConfig,
    RobotFeedback,
    Vector3,
    Workspace,
)


def main() -> None:
    receiver = CartesianReceiver(
        RobotFeedback(Pose(Vector3()), gripper=1.0),
        config=ReceiverConfig(
            Workspace(Vector3(-1, -1, -1), Vector3(1, 1, 1)),
            max_linear_speed=0.2,
            interpolation_time=0.04,
            command_timeout=0.15,
        ),
    )
    receiver.begin_session("example-calibration-1", now=0)
    command = PoseTarget(
        position=Vector3(0.1, 0, 0),
        orientation=None,
        gripper=0.5,
        session_id="example-calibration-1",
        sequence=1,
        source_frame_id=1,
        source_timestamp_us=1_000,
        clock_domain="example-camera",
        valid_for_s=0.1,
    )
    assert receiver.accept(command, now=0)
    for now in (0.025, 0.05, 0.1, 1.0):
        feedback = receiver.advance(now=now)
        print(f"t={now:.3f}s  x={feedback.pose.position.x:.3f}m  {receiver.status.state}")
    assert receiver.status.state == "expired"
    # Delayed old packets cannot restart output, even with another source timestamp.
    assert not receiver.accept(command, now=1.0)
    # A deliberate new calibration/session is required before accepting more output.
    receiver.begin_session("example-calibration-2", now=1.0)
    print("New session explicitly armed; waiting for a new command.")
    receiver.close(now=1.0)


if __name__ == "__main__":
    main()
