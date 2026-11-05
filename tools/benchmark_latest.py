"""Compare slow consumers of the same service; never sends robot commands.

Timestamp differences compare two clients of the same clock, not absolute camera
latency. Local frame age is measured immediately after each latest-mode read.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from pathlib import Path

from source_robotics_leap_motion import Tracker, __version__


def positive(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be positive and finite")
    return number


def distribution(values: list[float]) -> dict:
    ordered = sorted(values)
    return {
        "median": statistics.median(ordered),
        "p95": ordered[min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1)],
        "max": ordered[-1],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=positive, default=10)
    parser.add_argument("--consumer-rate", type=positive, default=20)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    factory = Tracker.demo if args.demo else Tracker
    gaps_ms: list[float] = []
    local_ages_ms: list[float] = []
    samples = 0
    hand_frames = 0
    with factory() as sequential, factory(mode="latest") as latest:
        started = time.perf_counter()
        cpu_started = time.process_time()
        while time.perf_counter() - started < args.duration:
            old = sequential.read()
            new = latest.read()
            health = latest.health
            if not args.demo and (old.clock_domain, old.device_id) != (
                new.clock_domain,
                new.device_id,
            ):
                raise RuntimeError("Clients are receiving different device clocks")
            if not args.demo:
                gaps_ms.append((new.timestamp_us - old.timestamp_us) / 1000)
            local_ages_ms.append(health.last_frame_age_s * 1000)
            hand_frames += bool(new.hands)
            samples += 1
            target = started + samples / args.consumer_rate
            time.sleep(max(0, min(target - time.perf_counter(), args.duration)))
        elapsed = time.perf_counter() - started
        cpu_seconds = time.process_time() - cpu_started
        result = {
            "package": __version__,
            "source": "synthetic" if args.demo else "live",
            "backend": latest.backend_name,
            "elapsed_s": elapsed,
            "consumer_fps": samples / elapsed,
            "delivered_samples": samples,
            "latest_hand_frames": hand_frames,
            "latest_local_receipt_age_ms": distribution(local_ages_ms),
            "latest_health": latest.health.to_dict(),
            "combined_client_cpu_percent_of_one_core": cpu_seconds / elapsed * 100,
        }
        if gaps_ms:
            result["latest_ahead_of_sequential_ms"] = {
                **distribution(gaps_ms),
                "first": gaps_ms[0],
                "last": gaps_ms[-1],
            }
    result["reader_closed"] = latest.health.status == "closed"
    text = json.dumps(result, indent=2, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
