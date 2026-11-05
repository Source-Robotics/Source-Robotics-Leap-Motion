import json
import subprocess
import sys
from pathlib import Path

from source_robotics_leap_motion.cli import main
from source_robotics_leap_motion.runtime import library_candidates


def test_cli_demo_json_contains_only_frames_on_stdout(capsys):
    assert main(["--demo", "--frames", "3", "--json"]) == 0
    captured = capsys.readouterr()
    frames = [json.loads(line) for line in captured.out.splitlines()]
    assert len(frames) == 3
    assert all(frame["clock_domain"] == "demo" for frame in frames)
    assert "synthetic" not in captured.out  # JSON is machine-readable, no banner.


def test_short_duration_exits_normally(capsys):
    assert main(["--demo", "--duration", "0.02"]) == 0


def test_cli_record_and_replay(tmp_path, capsys):
    path = tmp_path / "demo.jsonl"
    assert main(["record", str(path), "--demo", "--frames", "2"]) == 0
    capsys.readouterr()
    assert main(["replay", str(path), "--json"]) == 0
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 2


def test_missing_explicit_library_has_actionable_diagnostic(tmp_path, capsys):
    library = str(tmp_path / "LeapC.dll")
    assert main(["doctor", "--library", library, "--json", "--probe"]) == 2
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["checked_paths"] == [library]
    assert not report["probe"]["received_frame"]
    assert "Original Leap Motion Controller" in report["probe"]["error"]


def test_explicit_library_does_not_fall_back_to_an_unrelated_install(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_LEAP_LIBRARY", str(tmp_path / "other.dll"))
    explicit = tmp_path / "chosen.dll"
    assert library_candidates(explicit) == (explicit.resolve(),)


def test_import_has_no_native_loading_or_background_threads():
    script = (
        "import ctypes, threading; "
        "ctypes.CDLL = lambda *a, **k: (_ for _ in ()).throw(AssertionError('native load')); "
        "ctypes.WinDLL = ctypes.CDLL; "
        "before = set(threading.enumerate()); "
        "import source_robotics_leap_motion; "
        "assert set(threading.enumerate()) == before"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_record_does_not_create_file_when_tracking_cannot_open(tmp_path, capsys):
    path = tmp_path / "session.jsonl"
    result = main(
        ["record", str(path), "--library", str(tmp_path / "missing.dll"), "--frames", "1"]
    )
    assert result == 2
    assert not Path(path).exists()
