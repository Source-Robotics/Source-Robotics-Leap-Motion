"""Run with --demo to try the API before connecting a camera."""

import argparse

from source_robotics_leap_motion import Tracker

parser = argparse.ArgumentParser()
parser.add_argument("--demo", action="store_true")
args = parser.parse_args()

with Tracker.demo() if args.demo else Tracker() as tracker:
    for index, frame in enumerate(tracker):
        if hand := frame.right_hand:
            print(hand.palm.position)
        if index >= 9:
            break
