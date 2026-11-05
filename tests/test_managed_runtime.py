import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from source_robotics_leap_motion import Frame, Tracker
from source_robotics_leap_motion.backends import _job, managed
from source_robotics_leap_motion.cli import main
from source_robotics_leap_motion.errors import ConnectionError, RuntimeNotFoundError
from source_robotics_leap_motion.runtime_bundle import (
    CORE_FILES,
    DEPENDENCIES,
    MANIFEST,
    OPTIONAL_MODELS,
    inspect_runtime,
    prepare_local_runtime,
)


@pytest.fixture
def assets(tmp_path):
    source = tmp_path / "installed"
    source.mkdir()
    for name in CORE_FILES + DEPENDENCIES + OPTIONAL_MODELS:
        (source / name).write_bytes((name + " test fixture").encode())
    return source, tmp_path / "private"


def test_prepare_copies_only_core_and_dependencies_and_detects_corruption(assets):
    source, destination = assets
    (source / "LeapControlPanel.exe").write_bytes(b"not needed")
    report = prepare_local_runtime(source, destination)
    assert report["files"] == 7
    assert report["checksum_verified"]
    assert not report["redistribution_cleared"]
    assert {path.name for path in destination.iterdir()} == set(CORE_FILES + DEPENDENCIES) | {
        MANIFEST
    }
    # Idempotent adoption of matching files is allowed.
    assert prepare_local_runtime(source, destination) == report
    model = destination / "Tracking.ldat"
    original = model.read_bytes()
    model.write_bytes(b"X" + original[1:])
    with pytest.raises(RuntimeNotFoundError, match="checksum mismatch"):
        inspect_runtime(destination)


def test_prepare_never_overwrites_a_different_existing_engine(assets):
    source, destination = assets
    destination.mkdir()
    engine = destination / CORE_FILES[0]
    engine.write_bytes(b"keep this file")
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        prepare_local_runtime(source, destination)
    assert engine.read_bytes() == b"keep this file"
    assert not (destination / MANIFEST).exists()


def test_prepare_checks_missing_core_before_creating_destination(assets):
    source, destination = assets
    (source / "Tracking.ldat").unlink()
    with pytest.raises(RuntimeNotFoundError, match="Missing legacy runtime component"):
        prepare_local_runtime(source, destination)
    assert not destination.exists()


def test_prepare_supports_explicit_dependency_location_and_alternate_models(assets, tmp_path):
    source, destination = assets
    dependencies = tmp_path / "dependencies"
    dependencies.mkdir()
    for name in DEPENDENCIES:
        (source / name).rename(dependencies / name)
    report = prepare_local_runtime(
        source, destination, dependency_dir=dependencies, extra_models=True
    )
    assert report["files"] == 9
    assert all((destination / name).exists() for name in OPTIONAL_MODELS)


@pytest.mark.parametrize("change", ["escape", "duplicate", "missing", "engine", "oversize"])
def test_inspection_rejects_invalid_manifests(assets, change):
    source, destination = assets
    prepare_local_runtime(source, destination)
    path = destination / MANIFEST
    data = json.loads(path.read_text())
    if change == "escape":
        data["files"][0]["name"] = "../outside.exe"
    elif change == "duplicate":
        data["files"].append(data["files"][0])
    elif change == "missing":
        data["files"].pop(0)
    elif change == "engine":
        data["engine"] = "other.exe"
    path.write_text(" " * 65537 if change == "oversize" else json.dumps(data))
    with pytest.raises(RuntimeNotFoundError):
        inspect_runtime(destination)


def test_runtime_cli_prepare_and_inspect(assets, capsys):
    source, destination = assets
    assert main(["runtime", "prepare", str(source), "--destination", str(destination)]) == 0
    prepared = json.loads(capsys.readouterr().out)
    assert main(["runtime", "inspect", str(destination)]) == 0
    assert json.loads(capsys.readouterr().out) == prepared


@pytest.fixture
def launcher(assets, monkeypatch):
    source, destination = assets
    prepare_local_runtime(source, destination)
    monkeypatch.setattr(managed.sys, "platform", "win32")
    backend = Mock()
    backend.read.return_value = Frame(1, 1)
    backend_factory = Mock(return_value=backend)
    monkeypatch.setattr(managed, "LegacyWebSocketBackend", backend_factory)
    busy = Mock(return_value=False)
    monkeypatch.setattr(managed, "_port_in_use", busy)
    process = Mock(pid=12345, returncode=None)
    process.poll.return_value = None
    spawn = Mock(return_value=process)
    monkeypatch.setattr(managed.subprocess, "Popen", spawn)
    monkeypatch.setattr(managed.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    job = Mock()
    job_factory = Mock(return_value=job)
    monkeypatch.setattr(_job, "ProcessJob", job_factory)
    runtime = managed.ManagedLegacyBackend(destination)
    return SimpleNamespace(
        runtime=runtime,
        backend=backend,
        backend_factory=backend_factory,
        busy=busy,
        process=process,
        spawn=spawn,
        job=job,
        job_factory=job_factory,
        directory=destination,
    )


def test_existing_service_is_reused_without_owning_or_terminating_it(launcher):
    launcher.busy.return_value = True
    with Tracker(backend=launcher.runtime) as tracker:
        assert tracker.read() is launcher.backend.read.return_value
        assert tracker.runtime_details["mode"] == "existing"
        assert tracker.runtime_details["pid"] is None
    launcher.backend.close.assert_called_once()
    launcher.spawn.assert_not_called()
    launcher.job_factory.assert_not_called()


def test_exclusive_probe_never_stops_an_existing_service(launcher):
    launcher.busy.return_value = True
    launcher.runtime.reuse_existing = False
    with pytest.raises(ConnectionError, match="already in use"):
        launcher.runtime.open()
    launcher.spawn.assert_not_called()
    launcher.backend_factory.assert_not_called()


def test_private_engine_is_hidden_owned_and_closed(launcher):
    with Tracker(backend=launcher.runtime) as tracker:
        assert tracker.runtime_details["mode"] == "private"
        assert tracker.runtime_details["pid"] == 12345
        launcher.job.assign.assert_called_once_with(12345)
        arguments, options = launcher.spawn.call_args
        assert arguments[0][1] == "--run"
        assert options["creationflags"] == subprocess.CREATE_NO_WINDOW
        assert options["cwd"] == launcher.directory
        config = json.loads((launcher.directory / "state" / "config.json").read_text())
        assert not config["configuration"]["websockets_allow_remote"]
        assert config["configuration"]["images_mode"] == 0
        assert tracker.read() is launcher.backend.read.return_value
    launcher.process.terminate.assert_called_once()
    launcher.process.wait.assert_called_once_with(timeout=3)
    launcher.job.close.assert_called_once()
    assert launcher.runtime._log is None
    # Closing again must not touch any process, existing or private.
    launcher.runtime.close()
    launcher.process.terminate.assert_called_once()


@pytest.mark.parametrize("failure", ["job", "connect", "child_exit"])
def test_failed_startup_cleans_up_owned_process_and_job(launcher, failure):
    if failure == "job":
        launcher.job.assign.side_effect = OSError("job assignment failed")
    elif failure == "connect":
        launcher.backend.open.side_effect = KeyboardInterrupt
    else:
        launcher.process.poll.return_value = 7
        launcher.process.returncode = 7
    with pytest.raises((OSError, KeyboardInterrupt, ConnectionError)):
        launcher.runtime.open()
    launcher.job.close.assert_called_once()
    assert launcher.runtime._process is None
    assert launcher.runtime._log is None
    if failure != "child_exit":
        launcher.process.terminate.assert_called_once()


def test_unresponsive_owned_process_is_killed_on_close(launcher):
    launcher.runtime.open()
    launcher.process.wait.side_effect = [subprocess.TimeoutExpired("engine", 3), 0]
    launcher.runtime.close()
    launcher.process.kill.assert_called_once()
    launcher.job.close.assert_called_once()


def test_child_exit_is_reported_instead_of_reading_another_server(launcher):
    launcher.runtime.open()
    reads_at_startup = launcher.backend.read.call_count
    launcher.process.poll.return_value = 8
    launcher.process.returncode = 8
    try:
        with pytest.raises(ConnectionError, match="stopped with code 8"):
            launcher.runtime.read(1)
        assert launcher.backend.read.call_count == reads_at_startup
    finally:
        launcher.runtime.close()


def test_private_startup_requires_a_frame_and_preserves_it_for_the_caller(launcher):
    first, second = Frame(1, 1), Frame(2, 2)
    launcher.backend.read.side_effect = [first, second]
    with Tracker(backend=launcher.runtime) as tracker:
        launcher.backend.read.assert_called_once()
        assert tracker.read() is first
        launcher.backend.read.assert_called_once()  # No dropped startup frame or extra read.
        assert tracker.read() is second
        assert launcher.backend.read.call_count == 2


def test_socket_without_camera_frames_does_not_count_as_private_readiness(launcher):
    launcher.runtime.connect_timeout = 0.01
    launcher.backend.read.return_value = None
    with pytest.raises(ConnectionError, match="startup timed out"):
        launcher.runtime.open()
    launcher.backend.close.assert_called()
    launcher.process.terminate.assert_called_once()
    launcher.job.close.assert_called_once()
    assert launcher.runtime._pending_frame is None


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows process ownership")
def test_windows_job_closes_a_real_child_process():
    # No Leap service, camera, or elevation: exercise the actual Windows job API.
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    job = None
    try:
        job = _job.ProcessJob()
        job.assign(child.pid)
        assert child.poll() is None
        job.close()
        child.wait(timeout=3)  # Job termination can report exit code zero on Windows.
    finally:
        if job is not None:
            job.close()
        if child.poll() is None:
            child.kill()
            child.wait(timeout=3)


def test_runtime_selection_is_explicit():
    with pytest.raises(ValueError, match="Choose a backend"):
        Tracker(runtime_dir="runtime", library_path="LeapC.dll")
    with pytest.raises(ValueError, match="positive and finite"):
        managed.ManagedLegacyBackend("runtime", connect_timeout=float("nan"))
