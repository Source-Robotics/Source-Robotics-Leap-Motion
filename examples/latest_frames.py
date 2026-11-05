"""Read newest hand snapshots in a deliberately slower application loop."""

import time

from source_robotics_leap_motion import ConnectionError, Tracker, TrackingTimeoutError


def main() -> None:
    # Use Tracker.demo(mode="latest") to try this without hardware.
    with Tracker(mode="latest", max_frame_age=0.1) as tracker:
        while True:
            try:
                frame = tracker.read(timeout=0.25)
            except TrackingTimeoutError:  # Includes StaleFrameError.
                print("Waiting for fresh tracking:", tracker.health.to_dict())
                continue
            except ConnectionError:
                print("Tracking disconnected:", tracker.health.to_dict())
                break
            if hand := frame.right_hand:
                print(hand.palm.position)
            else:
                print("Camera streaming; no right hand visible")
            time.sleep(0.05)  # Other work: latest mode drains tracking independently.


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
