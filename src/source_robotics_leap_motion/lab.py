"""Loopback-only browser lab. Its only output adapter is SimulatedArm."""

from __future__ import annotations

import json
import queue
import secrets
import sys
import threading
import time
import webbrowser
from contextlib import nullcontext
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .adapters.simulated import SimulatedArm
from .backends.replay import ReplayBackend
from .control_config import GripperMapping, TeleoperationConfig, Workspace
from .control_models import Pose
from .errors import TeleoperationError, TrackingTimeoutError
from .mapping import Mapping
from .models import Vector3
from .teleoperation import Teleoperator
from .tracker import Tracker


def simulation_config() -> TeleoperationConfig:
    return TeleoperationConfig(
        workspace=Workspace(Vector3(0, -0.3, 0), Vector3(0.6, 0.3, 0.6)),
        max_linear_speed=0.2,
        max_angular_speed=1.0,
        mapping=Mapping(("-z", "-x", "y"), Vector3(0.75, 0.75, 0.75)),
        control_orientation=True,
        gripper=GripperMapping(),
    )


class LabServer:
    def __init__(self, port: int = 0) -> None:
        self.commands: queue.Queue[str] = queue.Queue(maxsize=16)
        self._lock = threading.Lock()
        self._state = b'{"state":"starting"}'
        self._token = secrets.token_urlsafe(32)
        self._html = (
            Path(__file__)
            .with_name("lab.html")
            .read_text(encoding="utf-8")
            .replace("__TOKEN__", self._token)
            .encode("utf-8")
        )
        self._assets = {
            "/lab.css": (
                Path(__file__).with_name("lab.css").read_bytes(),
                "text/css; charset=utf-8",
            ),
            "/lab.js": (
                Path(__file__).with_name("lab.js").read_bytes(),
                "text/javascript; charset=utf-8",
            ),
        }
        lab = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def reply(self, status, body, content_type="application/json; charset=utf-8"):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; "
                    "script-src 'self'; style-src 'self'; "
                    "frame-ancestors 'none'; base-uri 'none'",
                )
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == "/":
                    self.reply(200, lab._html, "text/html; charset=utf-8")
                elif self.path == "/state":
                    with lab._lock:
                        state = lab._state
                    self.reply(200, state)
                elif self.path in lab._assets:
                    self.reply(200, *lab._assets[self.path])
                else:
                    self.reply(404, b'{"error":"not found"}')

            def do_POST(self):
                if self.path != "/action":
                    self.reply(404, b'{"error":"not found"}')
                    return
                if (
                    self.headers.get("X-Source-Leap-Token") != lab._token
                    or self.headers.get("Origin", lab.url) != lab.url
                ):
                    self.reply(403, b'{"error":"invalid local session"}')
                    return
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 512:
                        raise ValueError("Invalid body size")
                    action = json.loads(self.rfile.read(size))["action"]
                    if action not in ("arm", "clutch", "resume", "disarm", "reconnect"):
                        raise ValueError("Unknown action")
                    lab.commands.put_nowait(action)
                except queue.Full:
                    self.reply(429, b'{"error":"action queue is full"}')
                    return
                except (ValueError, KeyError, TypeError):
                    self.reply(400, b'{"error":"invalid action"}')
                    return
                self.reply(202, b'{"accepted":true}')

        self._server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="source-leap-lab", daemon=True
        )

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}"

    def publish(self, state: dict) -> None:
        payload = json.dumps(state, allow_nan=False).encode("utf-8")
        with self._lock:
            self._state = payload

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_exc):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(2)


def snapshot(teleop: Teleoperator, robot: SimulatedArm, source: str, message: str) -> dict:
    status = teleop.status
    hand = (
        None
        if teleop.last_frame is None
        else next(
            (
                hand
                for hand in teleop.last_frame.hands
                if hand.handedness == teleop.config.handedness
            ),
            None,
        )
    )
    return {
        "schema": "source-leap.teleoperation-lab",
        "version": 1,
        "state": status.state,
        "reason": status.reason,
        "message": message,
        "source": source,
        "handedness": teleop.config.handedness,
        "hand": None if hand is None else {"id": hand.id, "position": asdict(hand.palm.position)},
        "robot": asdict(robot.read_feedback()),
        "control": asdict(status),
        "tracking": teleop.tracker.health.to_dict(),
        "config": asdict(teleop.config),
    }


def run_lab(args) -> int:
    if not 0 <= args.port <= 65535:
        raise ValueError("Viewer port must be between 0 and 65535")
    if args.json and not args.headless:
        raise ValueError("--json requires --headless")
    if args.demo and (args.library or args.runtime_dir or args.replay):
        raise ValueError("--demo cannot be combined with a live runtime or replay")
    if args.replay and (args.library or args.runtime_dir):
        raise ValueError("--replay cannot be combined with a live runtime")
    config = TeleoperationConfig.from_toml(args.config) if args.config else simulation_config()
    if args.demo:
        tracker = Tracker.demo(mode="latest", max_frame_age=config.max_frame_age)
        source = "synthetic hand"
    elif args.replay:
        tracker = Tracker(
            backend=ReplayBackend(args.replay, realtime=True),
            mode="latest",
            max_frame_age=config.max_frame_age,
        )
        source = "recorded hand"
    else:
        tracker = Tracker(
            mode="latest",
            library_path=args.library,
            runtime_dir=args.runtime_dir,
            max_frame_age=config.max_frame_age,
        )
        source = "Leap controller"
    center = (config.workspace.minimum + config.workspace.maximum) * 0.5
    robot = SimulatedArm(Pose(center))
    server = None if args.headless else LabServer(args.port)
    auto_pending = args.auto_arm
    processed = 0
    last_frame = None
    message = ""
    with (
        server if server is not None else nullcontext(),
        tracker,
        Teleoperator(tracker, robot=robot, config=config) as teleop,
    ):
        started = time.monotonic()
        if server is not None:
            server.publish(snapshot(teleop, robot, source, message))
            print("Teleoperation lab: " + server.url, flush=True)
            if not args.no_browser:
                webbrowser.open(server.url)
        try:
            while args.duration is None or time.monotonic() - started < args.duration:
                loop_started = time.monotonic()
                actions = []
                if server is not None:
                    while not server.commands.empty():
                        actions.append(server.commands.get_nowait())
                if auto_pending and not actions:
                    actions.append("arm")
                for action in actions:
                    try:
                        if action == "arm":
                            teleop.arm(timeout=0.05)
                            auto_pending = False
                        elif action == "clutch":
                            teleop.clutch()
                        elif action == "resume":
                            teleop.release_clutch()
                        elif action == "reconnect":
                            teleop.reconnect()
                        else:
                            auto_pending = False
                            teleop.disarm()
                        message = ""
                    except (TeleoperationError, TrackingTimeoutError) as error:
                        message = str(error)
                timeout = 0.05
                if args.duration is not None:
                    remaining = args.duration - (time.monotonic() - started)
                    if remaining <= 0:
                        break
                    timeout = min(timeout, remaining)
                teleop.step(timeout=timeout)
                state = snapshot(teleop, robot, source, message)
                if teleop.last_frame is not last_frame:
                    last_frame = teleop.last_frame
                    processed += 1
                    if args.json:
                        print(json.dumps(state, allow_nan=False, separators=(",", ":")))
                if server is not None:
                    server.publish(state)
                if args.frames is not None and processed >= args.frames:
                    break
                time.sleep(max(0.0, 1 / config.max_output_hz - (time.monotonic() - loop_started)))
        except StopIteration:
            pass
    print(
        f"Simulated targets: {robot.targets_sent}; tracking frames: {processed}.", file=sys.stderr
    )
    return 0
