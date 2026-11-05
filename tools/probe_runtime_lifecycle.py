"""Exercise private engine sharing, application crashes, and repeated startup."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from source_robotics_leap_motion import Tracker
from source_robotics_leap_motion.backends.managed import _port_in_use


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--crash-worker", action="store_true")
    args = parser.parse_args()
    directory = args.directory.resolve()
    cache = directory.parent.parent
    os.environ["SOURCE_LEAP_CACHE"] = str(cache)
    if args.crash_worker:
        with Tracker(timeout=10) as tracker:
            tracker.read()
            print("Worker received a frame; exiting without cleanup", flush=True)
            os._exit(17)
    if _port_in_use():
        raise RuntimeError(
            "Exclusive lifecycle test requires the installed Leap service to be stopped"
        )
    ready = cache / "engine/broker.json"
    report = {"directory": str(directory), "shared_frames": 0, "restart_cycles": 0}

    def wait_idle():
        deadline = time.perf_counter() + 8
        while time.perf_counter() < deadline:
            if not ready.exists() and not _port_in_use():
                return
            time.sleep(0.05)
        raise RuntimeError("Private engine did not shut down after the last client left")

    first = Tracker(timeout=10)
    second = Tracker(timeout=10)
    try:
        with first, second:
            assert first.runtime_details["mode"] == "shared-private"
            assert second.runtime_details["mode"] == "shared-private"
            first.read()
            second.read()
            first.close()
            for _ in range(30):
                second.read()
                report["shared_frames"] += 1
            report["second_client_survived_first_close"] = True
        wait_idle()
        report["last_client_shutdown"] = True
        for _ in range(2):
            with Tracker(timeout=10) as tracker:
                for _frame in range(10):
                    tracker.read()
            wait_idle()
            report["restart_cycles"] += 1
        crash = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), str(directory), "--crash-worker"],
            capture_output=True,
            text=True,
            timeout=18,
        )
        assert crash.returncode == 17, crash.stdout + crash.stderr
        wait_idle()
        report["crashed_application_cleanup"] = True
        report["passed"] = True
    except BaseException as error:
        report["error"] = str(error)
        report["passed"] = False
        raise
    finally:
        first.close()
        second.close()
        if args.summary:
            args.summary.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
