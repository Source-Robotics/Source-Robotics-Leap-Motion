"""Compare data delivery from the old SDK and current package on Windows.

Run this with the project venv. The old SDK worker needs a Python 3.8 interpreter
and the historical Leap.py/LeapPython.pyd in the project root. Nothing is sent to
a robot. Workers share a QPC clock and consume the same tracking service.
"""

import argparse
import ctypes
import json
import math
import platform
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KERNEL = ctypes.WinDLL("kernel32", use_last_error=True)
KERNEL.QueryPerformanceCounter.argtypes = [ctypes.POINTER(ctypes.c_int64)]
KERNEL.QueryPerformanceCounter.restype = ctypes.c_int
KERNEL.QueryPerformanceFrequency.argtypes = [ctypes.POINTER(ctypes.c_int64)]
KERNEL.QueryPerformanceFrequency.restype = ctypes.c_int
FREQUENCY = ctypes.c_int64()
KERNEL.QueryPerformanceFrequency(ctypes.byref(FREQUENCY))


def clock_ns():
    counter = ctypes.c_int64()
    KERNEL.QueryPerformanceCounter(ctypes.byref(counter))
    return counter.value * 1_000_000_000 // FREQUENCY.value


def percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def distribution(values):
    return {
        "count": len(values),
        "median": statistics.median(values) if values else None,
        "p95": percentile(values, 0.95),
        "min": min(values) if values else None,
        "max": max(values) if values else None,
    }


def old_snapshot(frame, palm_only=False):
    """Read equivalent common fields into Python-owned tuples through SWIG getters."""
    def vector(value, scale=0.001):
        return (value.x * scale, value.y * scale, value.z * scale)

    hands = []
    for hand in frame.hands:
        if palm_only:
            hands.append((vector(hand.palm_position), hand.grab_strength))
            continue
        fingers = []
        for finger in hand.fingers:
            bones = []
            for index in range(4):
                bone = finger.bone(index)
                bones.append((vector(bone.prev_joint), vector(bone.next_joint), bone.width * 0.001))
            fingers.append((finger.id, finger.type, finger.is_extended, tuple(bones)))
        arm = hand.arm
        hands.append((
            hand.id, hand.is_left, vector(hand.palm_position), vector(hand.palm_velocity),
            vector(hand.palm_normal, 1.0), vector(hand.direction, 1.0), hand.palm_width * 0.001,
            hand.grab_strength, hand.pinch_strength, hand.time_visible, tuple(fingers),
            vector(arm.elbow_position), vector(arm.wrist_position), arm.width * 0.001,
        ))
    return tuple(hands)


def summarize(samples, duration, cpu_seconds, errors):
    arrivals = [sample["ready_ns"] for sample in samples]
    hand_samples = [sample for sample in samples if sample["hands"]]
    return {
        "python": platform.python_version(),
        "duration_seconds": duration,
        "received_frames": len(samples),
        "unique_frame_ids": len({sample["id"] for sample in samples}),
        "frames_per_second": len(samples) / duration,
        "hand_frames": len(hand_samples),
        "cpu_seconds": cpu_seconds,
        "cpu_percent_of_one_core": cpu_seconds / duration * 100,
        "interarrival_ms": distribution([
            (later - earlier) / 1_000_000 for earlier, later in zip(arrivals, arrivals[1:])
        ]),
        "hand_processing_us": distribution([sample["processing_us"] for sample in hand_samples]),
        "empty_processing_us": distribution([
            sample["processing_us"] for sample in samples if not sample["hands"]
        ]),
        "errors": errors,
    }


def old_worker(args):
    sys.path.insert(0, str(ROOT))
    import Leap

    samples = []
    errors = []
    end = args.start_ns + round(args.duration * 1_000_000_000)
    lock = threading.Lock()

    class Listener(Leap.Listener):
        def on_frame(self, controller):
            entry = clock_ns()
            if not args.start_ns <= entry < end:
                return
            try:
                frame = controller.frame()
                if frame.id < 0:
                    return
                data = old_snapshot(frame, palm_only=args.worker == "old-palm")
                ready = clock_ns()
                sample = {
                    "id": frame.id, "timestamp_us": frame.timestamp,
                    "ready_ns": ready, "hands": len(data),
                    "processing_us": (ready - entry) / 1000,
                }
                with lock:
                    samples.append(sample)
            except Exception as error:
                errors.append(str(error))

    controller = Leap.Controller()
    listener = Listener()
    controller.add_listener(listener)
    controller.set_policy(Leap.Controller.POLICY_BACKGROUND_FRAMES)
    try:
        while clock_ns() < args.start_ns:
            time.sleep(0.001)
        cpu_start = time.process_time()
        while clock_ns() < end:
            time.sleep(0.01)
        cpu = time.process_time() - cpu_start
    finally:
        controller.remove_listener(listener)
    with lock:
        copied = list(samples)
    return {"summary": summarize(copied, args.duration, cpu, errors), "samples": copied}


def new_worker(args):
    from source_robotics_leap_motion import Tracker
    from source_robotics_leap_motion.backends.legacy import LegacyWebSocketBackend

    backend = LegacyWebSocketBackend()
    samples = []
    end = args.start_ns + round(args.duration * 1_000_000_000)
    raw_hand = None
    with Tracker(backend=backend, timeout=3) as tracker:
        original_recv = backend._socket.recv
        last = {}

        def observed_recv():
            raw = original_recv()
            last["received_ns"] = clock_ns()
            last["raw"] = raw
            return raw

        backend._socket.recv = observed_recv
        # Drain warm-up frames to avoid measuring an artificial connection backlog.
        while clock_ns() < args.start_ns:
            tracker.read()
        cpu_start = time.process_time()
        while clock_ns() < end:
            frame = tracker.read()
            ready = clock_ns()
            if ready >= end:
                break
            samples.append({
                "id": frame.id, "timestamp_us": frame.timestamp_us, "ready_ns": ready,
                "hands": len(frame.hands),
                "processing_us": (ready - last["received_ns"]) / 1000,
            })
            if frame.hands and raw_hand is None:
                raw_hand = last["raw"]
        cpu = time.process_time() - cpu_start
    result = {"summary": summarize(samples, args.duration, cpu, []), "samples": samples}
    if raw_hand:
        raw_path = Path(args.output).with_name("raw-hand-frame.json")
        raw_path.write_text(raw_hand, encoding="utf-8")
        result["raw_hand_fixture"] = str(raw_path)
    return result


def compare(args):
    output = Path(args.output or ROOT / ".tools" / "benchmarks" / str(time.time_ns()))
    output.mkdir(parents=True, exist_ok=True)
    start = clock_ns() + 5_000_000_000
    workers = []
    for mode, python in (
        ("old-palm", args.old_python), ("old-full", args.old_python), ("new", sys.executable)
    ):
        path = output / (mode + ".json")
        process = subprocess.Popen([
            str(python), str(Path(__file__).resolve()), "--worker", mode,
            "--duration", str(args.duration), "--start-ns", str(start), "--output", str(path),
        ], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        workers.append((mode, process, path))
    data = {}
    for mode, process, path in workers:
        stdout, stderr = process.communicate(timeout=args.duration + 20)
        if process.returncode:
            raise RuntimeError(mode + ": " + stdout + stderr)
        data[mode] = json.loads(path.read_text(encoding="utf-8"))
    result = {mode: item["summary"] for mode, item in data.items()}
    new_samples = {(s["id"], s["timestamp_us"]): s for s in data["new"]["samples"]}
    for mode in ("old-palm", "old-full"):
        differences = []
        hand_differences = []
        for sample in data[mode]["samples"]:
            other = new_samples.get((sample["id"], sample["timestamp_us"]))
            if other is not None:
                delta_us = (other["ready_ns"] - sample["ready_ns"]) / 1000
                differences.append(delta_us)
                if sample["hands"] and other["hands"]:
                    hand_differences.append(delta_us)
        result["new_ready_minus_" + mode + "_us"] = distribution(differences)
        result["new_ready_minus_" + mode + "_hand_us"] = distribution(hand_differences)
    (output / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print("Results:", output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-python", type=Path, default=ROOT / ".tools/python38/python.exe")
    parser.add_argument("--duration", type=float, default=15)
    parser.add_argument("--output")
    parser.add_argument("--worker", choices=("old-palm", "old-full", "new"))
    parser.add_argument("--start-ns", type=int)
    args = parser.parse_args()
    if not math.isfinite(args.duration) or args.duration <= 0:
        parser.error("--duration must be positive and finite")
    if args.worker:
        result = new_worker(args) if args.worker == "new" else old_worker(args)
        Path(args.output).write_text(json.dumps(result), encoding="utf-8")
    else:
        compare(args)


if __name__ == "__main__":
    main()
