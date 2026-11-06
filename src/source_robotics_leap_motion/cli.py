"""Command line monitor, diagnostics, recording, and replay."""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from contextlib import nullcontext

from . import __version__
from .backends.replay import ReplayBackend
from .errors import LeapError, TrackingTimeoutError
from .recording import Recorder, frame_to_dict
from .runtime import diagnose
from .runtime_bundle import inspect_runtime, prepare_local_runtime
from .tracker import Tracker


def _positive_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be positive and finite")
    return number


def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def _tracking_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--demo", action="store_true", help="use synthetic hands; no hardware needed"
    )
    parser.add_argument("--frames", type=_positive_int, help="stop after this many frames")
    parser.add_argument("--duration", type=_positive_float, help="stop after this many seconds")
    parser.add_argument("--json", action="store_true", help="write every frame as JSON Lines")
    parser.add_argument(
        "--latest", action="store_true", help="keep only the newest unread frame; may skip frames"
    )
    parser.add_argument(
        "--max-frame-age",
        type=_positive_float,
        default=0.1,
        help="latest-mode local receipt age limit in seconds (default: 0.1)",
    )
    parser.add_argument(
        "--health",
        action="store_true",
        help="write health JSON to stderr while streaming and on exit",
    )
    runtime = parser.add_mutually_exclusive_group()
    runtime.add_argument("--library", help="explicit LeapC library path for development")
    runtime.add_argument("--runtime-dir", help="use a prepared local legacy runtime if needed")
    parser.add_argument(
        "--timeout", type=_positive_float, default=5, help="tracking deadline in seconds"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="source-leap", description="Leap Motion tracking tools")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("setup", help="check device access and prepare tracking")
    setup.add_argument(
        "--archive", help="install a local runtime release archive without downloading"
    )
    setup.add_argument("--catalog", help="release catalog path for deployment/testing")
    setup.add_argument(
        "--download-only", action="store_true", help="prepare runtime without opening the camera"
    )
    setup.add_argument(
        "--install-driver",
        action="store_true",
        help="request Windows approval for a missing driver",
    )
    setup.add_argument(
        "--open-downloads", action="store_true", help="open the official platform setup page"
    )
    setup.add_argument("--json", action="store_true")
    setup.add_argument("--timeout", type=_positive_float, default=10)
    monitor = commands.add_parser("monitor", help="show hands (default command)")
    _tracking_options(monitor)
    doctor = commands.add_parser("doctor", help="inspect runtime prerequisites")
    doctor.add_argument("--json", action="store_true")
    runtime = doctor.add_mutually_exclusive_group()
    runtime.add_argument("--library")
    runtime.add_argument("--runtime-dir")
    doctor.add_argument("--probe", action="store_true", help="also attempt to receive a live frame")
    doctor.add_argument("--timeout", type=_positive_float, default=3)
    record = commands.add_parser("record", help="record a new JSON Lines session")
    record.add_argument("path")
    record.add_argument("--overwrite", action="store_true", help="replace an existing recording")
    _tracking_options(record)
    replay = commands.add_parser("replay", help="inspect a recorded session")
    replay.add_argument("path")
    replay.add_argument("--realtime", action="store_true", help="pace using recorded timestamps")
    replay.add_argument("--speed", type=_positive_float, default=1)
    replay.add_argument("--frames", type=_positive_int)
    replay.add_argument("--duration", type=_positive_float)
    replay.add_argument("--json", action="store_true")
    replay.add_argument("--health", action="store_true")
    replay.add_argument("--timeout", type=_positive_float, default=5)
    lab = commands.add_parser("teleop", help="inspect hand control with a simulated Cartesian arm")
    lab.add_argument("--demo", action="store_true", help="use a synthetic hand")
    lab.add_argument("--replay", help="use a recorded hand session at recorded speed")
    lab.add_argument("--config", help="teleoperation TOML with workspace and speed limits")
    lab.add_argument("--headless", action="store_true", help="run without the browser viewer")
    lab.add_argument(
        "--auto-arm", action="store_true", help="automatically calibrate the simulated arm once"
    )
    lab.add_argument("--json", action="store_true", help="headless lab telemetry as JSON Lines")
    lab.add_argument(
        "--no-browser", action="store_true", help="print the viewer URL without opening it"
    )
    lab.add_argument(
        "--port", type=int, default=0, help="loopback viewer port; zero selects a free port"
    )
    lab.add_argument("--duration", type=_positive_float)
    lab.add_argument("--frames", type=_positive_int)
    runtime = lab.add_mutually_exclusive_group()
    runtime.add_argument("--library")
    runtime.add_argument("--runtime-dir")
    runtime = commands.add_parser("runtime", help="prepare or inspect a local runtime prototype")
    actions = runtime.add_subparsers(dest="runtime_action", required=True)
    prepare = actions.add_parser(
        "prepare", help="copy the core from an existing local installation"
    )
    prepare.add_argument("source")
    prepare.add_argument("--destination", required=True)
    prepare.add_argument("--dependencies", help="directory containing the VC++ runtime DLLs")
    prepare.add_argument(
        "--extra-models", action="store_true", help="also copy alternate model files"
    )
    inspect = actions.add_parser("inspect", help="verify the local bundle's file checksums")
    inspect.add_argument("directory")
    probe = actions.add_parser("probe", help="test tracking through a local runtime")
    probe.add_argument("directory")
    probe.add_argument(
        "--exclusive", action="store_true", help="refuse reuse of an existing service"
    )
    probe.add_argument("--frames", type=_positive_int, default=30)
    probe.add_argument("--timeout", type=_positive_float, default=10)
    return parser


def _setup(args) -> int:
    from .delivery import cached_runtime, ensure_runtime, install_archive
    from .setup import install_windows_driver, setup_report

    if args.archive:
        install_archive(args.archive)
    if args.download_only or args.catalog:
        ensure_runtime(catalog=args.catalog)
    report = setup_report()
    if args.open_downloads:
        import webbrowser

        report["download_page_opened"] = webbrowser.open(report["download_url"])
    needs_driver = report["device"]["status"] == "driver-required"
    install_driver = args.install_driver
    interactive = sys.stdin.isatty() and not args.json
    if needs_driver and not install_driver and interactive:
        install_driver = input(
            "Windows reports a missing Leap driver. Install it now? [y/N] "
        ).strip().lower() in ("y", "yes")
    if install_driver:
        directory = cached_runtime() or ensure_runtime(catalog=args.catalog)
        report["driver_setup"] = install_windows_driver(directory)
        report["device"] = setup_report()["device"]
    exit_code = 0
    if not args.download_only:
        try:
            with Tracker(timeout=args.timeout) as tracker:
                frame = tracker.read()
                report["tracking"] = {
                    "ready": True,
                    "backend": tracker.backend_name,
                    "hands": len(frame.hands),
                    "runtime": tracker.runtime_details,
                }
        except LeapError as exc:
            report["tracking"] = {"ready": False, "error": str(exc)}
            exit_code = 2
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Platform: {report['platform']}")
        print(f"Controller: {report['device']['status']}")
        print(f"Runtime cache: {report['cached_runtime'] or 'not installed'}")
        if "tracking" in report:
            tracking = report["tracking"]
            print("Tracking: ready" if tracking["ready"] else "Tracking: " + tracking["error"])
        if exit_code:
            for instruction in report["instructions"]:
                print(instruction)
            print("Setup instructions: " + report["download_url"])
    return exit_code


def _doctor(args) -> int:
    report = diagnose(args.library).to_dict()
    exit_code = 0 if report["library"] or report["cached_runtime"] else 2
    if args.probe:
        try:
            with Tracker(
                library_path=args.library, runtime_dir=args.runtime_dir, timeout=args.timeout
            ) as tracker:
                report["selected_backend"] = tracker.backend_name
                if tracker.runtime_details is not None:
                    report["local_runtime"] = tracker.runtime_details
                frame = tracker.read()
            report["probe"] = {"received_frame": True, "hands": len(frame.hands)}
            exit_code = 0
        except LeapError as exc:
            report["probe"] = {"received_frame": False, "error": str(exc)}
            exit_code = 2
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Source Robotics Leap Motion {__version__}")
        print(f"Python: {report['python']} ({report['architecture_bits']}-bit)")
        print(f"Interpreter: {report['executable']}")
        print(f"LeapC: {report['library'] or 'not found'}")
        print(f"Cached runtime: {report['cached_runtime'] or 'not installed'}")
        service = report["service_executable"] or "not detected in Windows registry"
        print(f"Tracking service: {service}")
        for note in report["notes"]:
            print(f"- {note}")
        if "probe" in report:
            probe = report["probe"]
            print(
                "Probe: "
                + (
                    f"received a frame with {probe['hands']} hand(s)"
                    if probe["received_frame"]
                    else probe["error"]
                )
            )
        if exit_code:
            print(f"Runtime download: {report['download_url']}")
    return exit_code


def _runtime(args) -> int:
    if args.runtime_action == "prepare":
        result = prepare_local_runtime(
            args.source,
            args.destination,
            dependency_dir=args.dependencies,
            extra_models=args.extra_models,
        )
    elif args.runtime_action == "inspect":
        result = inspect_runtime(args.directory)
    else:
        from .backends.managed import ManagedLegacyBackend

        if args.exclusive:
            backend = ManagedLegacyBackend(
                args.directory, connect_timeout=args.timeout, reuse_existing=False
            )
        else:
            from .backends.shared import SharedRuntimeBackend

            backend = SharedRuntimeBackend(args.directory, connect_timeout=args.timeout)
        with Tracker(backend=backend, timeout=args.timeout) as tracker:
            hand_frames = 0
            for _ in range(args.frames):
                hand_frames += bool(tracker.read().hands)
            result = {
                **backend.details,
                "frames": args.frames,
                "hand_frames": hand_frames,
            }
    print(json.dumps(result, indent=2))
    return 0


def _run(args) -> int:
    mode = "latest" if getattr(args, "latest", False) else "sequential"
    max_age = getattr(args, "max_frame_age", 0.1)
    if args.command == "replay":
        tracker = Tracker(
            backend=ReplayBackend(args.path, realtime=args.realtime, speed=args.speed),
            timeout=args.timeout,
        )
    elif args.demo:
        if args.library or args.runtime_dir:
            raise ValueError("--demo cannot be combined with a runtime or library selection")
        tracker = Tracker.demo(mode=mode, max_frame_age=max_age, timeout=args.timeout)
    else:
        tracker = Tracker(
            library_path=args.library,
            runtime_dir=args.runtime_dir,
            timeout=args.timeout,
            mode=mode,
            max_frame_age=max_age,
        )
    count = 0
    last_print = -math.inf
    last_health = time.perf_counter()
    started = time.perf_counter()
    recorder = Recorder(args.path, overwrite=args.overwrite) if args.command == "record" else None
    # Open tracking first so a missing runtime does not create an empty recording.
    with tracker, recorder if recorder is not None else nullcontext():
        started = time.perf_counter()
        if not args.json:
            source = (
                "recording"
                if args.command == "replay"
                else "DEMO (synthetic)"
                if args.demo
                else "live"
            )
            print(f"Source: {source}. Positions in metres. Ctrl+C to stop.", file=sys.stderr)
        last_health = started
        try:
            while True:
                elapsed = time.perf_counter() - started
                if args.duration is not None and elapsed >= args.duration:
                    break
                timeout = args.timeout
                if args.duration is not None:
                    timeout = min(timeout, args.duration - elapsed)
                try:
                    frame = tracker.read(timeout=timeout)
                except StopIteration:
                    break
                except TrackingTimeoutError:
                    if args.duration is not None and time.perf_counter() - started >= args.duration:
                        break
                    raise
                if recorder is not None:
                    recorder.write(frame)
                count += 1
                now = time.perf_counter()
                if args.json:
                    print(json.dumps(frame_to_dict(frame), allow_nan=False, separators=(",", ":")))
                elif now - last_print >= 0.1:
                    description = (
                        " | ".join(
                            f"{hand.handedness} #{hand.id}: "
                            f"({hand.palm.position.x:+.3f}, {hand.palm.position.y:+.3f}, "
                            f"{hand.palm.position.z:+.3f}) grab={hand.grab_strength:.2f}"
                            for hand in frame.hands
                        )
                        or "no hands"
                    )
                    print(f"Frame {frame.id}: {description}", flush=True)
                    last_print = now
                if args.health and now - last_health >= 1:
                    _print_health(tracker)
                    last_health = now
                if args.frames is not None and count >= args.frames:
                    break
        finally:
            if args.health:
                _print_health(tracker)
    print(f"Processed {count} frame(s).", file=sys.stderr)
    return 0


def _print_health(tracker: Tracker) -> None:
    print(
        json.dumps({"tracking_health": tracker.health.to_dict()}, allow_nan=False), file=sys.stderr
    )


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    commands = {
        "monitor",
        "doctor",
        "setup",
        "record",
        "replay",
        "runtime",
        "teleop",
        "--version",
        "--help",
        "-h",
    }
    if not arguments or arguments[0] not in commands:
        arguments.insert(0, "monitor")
    args = _parser().parse_args(arguments)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        if args.command == "setup":
            return _setup(args)
        if args.command == "doctor":
            return _doctor(args)
        if args.command == "runtime":
            return _runtime(args)
        if args.command == "teleop":
            from .lab import run_lab

            return run_lab(args)
        return _run(args)
    except KeyboardInterrupt:
        print("Stopped.", file=sys.stderr)
        return 130
    except (LeapError, OSError, ValueError) as exc:
        if (
            args.command == "monitor"
            and not args.demo
            and not args.json
            and args.library is None
            and args.runtime_dir is None
            and sys.stdin.isatty()
        ):
            print(str(exc), file=sys.stderr)
            if input("Run tracking setup now? [Y/n] ").strip().lower() in ("", "y", "yes"):
                try:
                    result = _setup(_parser().parse_args(["setup"]))
                    return _run(args) if result == 0 else result
                except (LeapError, OSError, ValueError) as setup_error:
                    print(f"source-leap: {setup_error}", file=sys.stderr)
                    return 2
        print(f"source-leap: {exc}", file=sys.stderr)
        return 2
