"""Bounded, read-only camera test of a private runtime. Does not control services."""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from contextlib import nullcontext
from pathlib import Path

from source_robotics_leap_motion import LeapError, Recorder, Tracker, TrackingTimeoutError
from source_robotics_leap_motion.backends.managed import ManagedLegacyBackend
from source_robotics_leap_motion.runtime_bundle import file_hash


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--duration", type=float, default=5)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--record", type=Path)
    args = parser.parse_args()
    if not math.isfinite(args.duration) or not 1 <= args.duration <= 15:
        parser.error("--duration must be between 1 and 15 seconds")
    system_config = (
        Path(os.environ.get("ProgramData", "C:/ProgramData")) / "Leap Motion" / "config.json"
    )
    before = file_hash(system_config) if system_config.is_file() else None
    backend = ManagedLegacyBackend(args.directory, connect_timeout=10, reuse_existing=False)
    report = {
        "directory": str(args.directory.resolve()),
        "frames": 0,
        "hand_frames": 0,
        "full_skeleton_hands": 0,
        "arm_samples": 0,
    }
    handedness = set()
    recorder = Recorder(args.record) if args.record else None

    def observe(frame):
        report["frames"] += 1
        report["hand_frames"] += bool(frame.hands)
        for hand in frame.hands:
            handedness.add(hand.handedness)
            report["full_skeleton_hands"] += len(hand.fingers) == 5 and all(
                len(finger.bones) == 4 for finger in hand.fingers
            )
            report["arm_samples"] += hand.arm is not None
        if recorder is not None:
            recorder.write(frame)

    child = None
    first_arrival = last_arrival = None
    exit_code = 0
    started = time.perf_counter()
    try:
        with (
            Tracker(backend=backend, timeout=2) as tracker,
            recorder if recorder is not None else nullcontext(),
        ):
            report.update(backend.details)
            child = backend._process  # Keep the owned handle to verify exit after context cleanup.
            report["connection_seconds"] = time.perf_counter() - started
            # The socket can be ready before the camera and model finish loading.
            startup_deadline = time.perf_counter() + 15
            while True:
                remaining = startup_deadline - time.perf_counter()
                if remaining <= 0:
                    raise TrackingTimeoutError(
                        "Private engine produced no frames during 15s startup"
                    )
                try:
                    frame = tracker.read(timeout=min(2, remaining))
                    break
                except TrackingTimeoutError:
                    continue
            first_arrival = last_arrival = time.perf_counter()
            report["first_frame_seconds"] = first_arrival - started
            observe(frame)
            deadline = time.perf_counter() + args.duration
            while time.perf_counter() < deadline:
                frame = tracker.read()
                last_arrival = time.perf_counter()
                if first_arrival is None:
                    first_arrival = last_arrival
                observe(frame)
    except (LeapError, OSError) as error:
        report["error"] = str(error)
        exit_code = 2
    finally:
        report["child_exited"] = child.poll() is not None if child is not None else None
        report["handedness_seen"] = sorted(handedness)
        if args.record is not None:
            report["recording"] = str(args.record.resolve())
        after = file_hash(system_config) if system_config.is_file() else None
        report["system_config_unchanged"] = before == after if before is not None else None
        if first_arrival is not None and last_arrival > first_arrival:
            elapsed = last_arrival - first_arrival
            report["capture_seconds"] = elapsed
            report["observed_fps"] = (report["frames"] - 1) / elapsed
        output = args.summary or args.directory / "state" / "probe-summary.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
