import json
from dataclasses import replace

import pytest
from test_tracking import native_event

from source_robotics_leap_motion import Recorder, RecordingError, Tracker, read_recording
from source_robotics_leap_motion.backends.leapc import copy_frame
from source_robotics_leap_motion.backends.replay import ReplayBackend
from source_robotics_leap_motion.recording import frame_from_dict, frame_to_dict


def test_skeleton_and_empty_frames_round_trip(tmp_path):
    event, _hands = native_event()
    frames = [copy_frame(event, 3), replace(copy_frame(event, 3), id=8, hands=())]
    path = tmp_path / "session.jsonl"
    with Recorder(path) as recorder:
        for frame in frames:
            recorder.write(frame)
    assert list(read_recording(path)) == frames
    with Tracker(backend=ReplayBackend(path)) as tracker:
        assert list(tracker) == frames


def test_existing_recording_is_not_overwritten(tmp_path):
    path = tmp_path / "session.jsonl"
    path.write_text("important recording", encoding="utf-8")
    with pytest.raises(FileExistsError), Recorder(path):
        pass
    assert path.read_text(encoding="utf-8") == "important recording"


@pytest.mark.parametrize("field,value", [("version", 999), ("units", "millimetres")])
def test_incompatible_recording_is_rejected(tmp_path, field, value):
    path = tmp_path / "session.jsonl"
    with Recorder(path):
        pass
    header = json.loads(path.read_text(encoding="utf-8"))
    header[field] = value
    path.write_text(json.dumps(header) + "\n", encoding="utf-8")
    with pytest.raises(RecordingError):
        list(read_recording(path))


def test_truncated_frame_reports_line_number(tmp_path):
    path = tmp_path / "session.jsonl"
    with Recorder(path):
        pass
    with path.open("a", encoding="utf-8") as stream:
        stream.write('{"frame":')
    with pytest.raises(RecordingError, match="line 2"):
        list(read_recording(path))


def test_non_finite_recording_values_are_rejected():
    with Tracker.demo(realtime=False) as tracker:
        data = json.loads(json.dumps(frame_to_dict(tracker.read())))
    data["hands"][0]["palm"]["position"]["x"] = float("nan")
    with pytest.raises(RecordingError, match="finite"):
        frame_from_dict(data)


def test_paced_replay_rejects_clock_reset(tmp_path):
    path = tmp_path / "session.jsonl"
    with Tracker.demo(realtime=False) as tracker:
        frame = tracker.read()
    with Recorder(path) as recorder:
        recorder.write(replace(frame, timestamp_us=100))
        recorder.write(replace(frame, timestamp_us=99))
    with Tracker(backend=ReplayBackend(path, realtime=True)) as tracker:
        tracker.read()
        with pytest.raises(RecordingError, match="monotonically"):
            tracker.read()
