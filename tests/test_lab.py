import json
import urllib.error
import urllib.request
from urllib.parse import urlsplit

import pytest

from source_robotics_leap_motion.cli import main
from source_robotics_leap_motion.lab import LabServer


def test_headless_demo_starts_disarmed_and_never_sends_without_activation(capsys):
    assert main(["teleop", "--demo", "--headless", "--json", "--frames", "3"]) == 0
    captured = capsys.readouterr()
    states = [json.loads(line) for line in captured.out.splitlines()]
    assert len(states) == 3
    assert all(state["state"] == "disarmed" for state in states)
    assert all(state["control"]["sequence"] == 0 for state in states)
    assert "Simulated targets: 0" in captured.err


def test_headless_demo_can_explicitly_arm_simulation(capsys):
    assert main(["teleop", "--demo", "--headless", "--auto-arm", "--json", "--frames", "3"]) == 0
    states = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(states) == 3
    assert states[-1]["state"] == "active"
    assert states[-1]["control"]["sequence"] > 0


def test_headless_demo_can_use_the_interpolating_receiver_and_closes_its_worker(capsys):
    import threading

    assert (
        main(
            [
                "teleop",
                "--demo",
                "--interpolate",
                "--headless",
                "--auto-arm",
                "--json",
                "--frames",
                "3",
            ]
        )
        == 0
    )
    states = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(states) == 3
    assert states[-1]["receiver"]["accepted_commands"] > 0
    assert states[-1]["receiver"]["session_id"] == states[-1]["control"]["session_id"]
    assert not any(t.name == "source-leap-receiver" for t in threading.enumerate())


def test_lab_server_serves_packaged_viewer_and_authenticated_bounded_actions():
    server = LabServer()
    with server:
        server.publish({"state": "disarmed"})
        with urllib.request.urlopen(server.url, timeout=3) as response:
            html = response.read().decode()
            assert "Teleoperation lab" in html
            assert "__TOKEN__" not in html
            assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
        with urllib.request.urlopen(server.url + "/state", timeout=3) as response:
            assert json.load(response) == {"state": "disarmed"}
        for asset, content_type in [("lab.js", "text/javascript"), ("lab.css", "text/css")]:
            with urllib.request.urlopen(server.url + "/" + asset, timeout=3) as response:
                assert response.headers["Content-Type"].startswith(content_type)
                assert len(response.read()) > 100

        def action(token, origin, body=b'{"action":"arm"}'):
            request = urllib.request.Request(
                server.url + "/action",
                data=body,
                headers={"X-Source-Leap-Token": token, "Origin": origin},
                method="POST",
            )
            return urllib.request.urlopen(request, timeout=3)

        for token, origin in [("wrong", server.url), (server._token, "https://example.com")]:
            with pytest.raises(urllib.error.HTTPError) as caught:
                action(token, origin)
            assert caught.value.code == 403
        with action(server._token, server.url) as response:
            assert response.status == 202
        assert server.commands.get_nowait() == "arm"
        with pytest.raises(urllib.error.HTTPError) as caught:
            action(server._token, server.url, b'{"action":"arbitrary_robot_command"}')
        assert caught.value.code == 400
        for _ in range(16):
            server.commands.put_nowait("arm")
        with pytest.raises(urllib.error.HTTPError) as caught:
            action(server._token, server.url)
        assert caught.value.code == 429
    assert not server._thread.is_alive()


def test_lab_port_cannot_be_shared_by_two_simulator_processes():
    with LabServer() as server:
        with pytest.raises(OSError):
            LabServer(urlsplit(server.url).port)


@pytest.mark.parametrize(
    "arguments",
    [
        ["--json"],
        ["--demo", "--replay", "anything.jsonl"],
        ["--port", "-1"],
    ],
)
def test_invalid_lab_options_report_errors(arguments, capsys):
    assert main(["teleop", *arguments]) == 2
