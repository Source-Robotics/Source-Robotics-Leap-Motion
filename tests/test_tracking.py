import ctypes as C
import math

import pytest

from source_robotics_leap_motion import (
    ConnectionError,
    Frame,
    Tracker,
    TrackingTimeoutError,
    Vector3,
)
from source_robotics_leap_motion.backends._native import NativeHand, NativeTrackingEvent
from source_robotics_leap_motion.backends.leapc import copy_frame


def native_event():
    hand = NativeHand()
    hand.id = 42
    hand.type = 1
    hand.palm.position.x = 125
    hand.palm.position.y = 250
    hand.palm.velocity.z = 1000
    hand.palm.orientation.w = 1
    hand.arm.rotation.w = 1
    for digit in hand.digits:
        for bone in digit.bones:
            bone.rotation.w = 1
    hand.digits[1].bones[3].next_joint.x = 200
    hands = (NativeHand * 1)(hand)
    event = NativeTrackingEvent()
    event.info.timestamp = 123456
    event.tracking_frame_id = 7
    event.nHands = 1
    event.pHands = hands
    event.framerate = 120
    return event, hands


def test_native_snapshot_owns_memory_and_converts_units():
    event, hands = native_event()
    frame = copy_frame(event, device_id=3)
    hands[0].palm.position.x = 99999
    hands[0].digits[1].bones[3].next_joint.x = 99999
    assert frame.right_hand.id == 42
    assert frame.right_hand.palm.position == Vector3(0.125, 0.25, 0)
    assert frame.right_hand.palm.velocity.z == 1
    assert frame.right_hand.fingers[1].bones[3].next_joint.x == pytest.approx(0.2)
    assert frame.device_id == 3
    assert frame.timestamp_us == 123456


@pytest.mark.parametrize("count", [1, 999])
def test_native_rejects_impossible_or_null_hand_arrays(count):
    event = NativeTrackingEvent()
    event.nHands = count
    with pytest.raises(ValueError):
        copy_frame(event, 0)


def test_no_hands_is_a_valid_frame():
    frame = copy_frame(NativeTrackingEvent(), 0)
    assert frame.hands == ()
    assert frame.right_hand is None
    assert frame.left_hand is None


def test_native_rejects_non_finite_position():
    event, _hands = native_event()
    event.pHands[0].palm.position.x = math.nan
    with pytest.raises(ValueError, match="finite"):
        copy_frame(event, 0)


class Source:
    def __init__(self):
        self.closed = 0

    def open(self):
        pass

    def read(self, timeout):
        return None

    def close(self):
        self.closed += 1


def test_timeout_is_distinct_from_empty_frame_and_closes_connection():
    source = Source()
    with pytest.raises(TrackingTimeoutError), Tracker(backend=source) as tracker:
        tracker.read(timeout=0.01)
    assert source.closed == 1


def test_source_is_closed_even_if_open_fails():
    class FailedSource(Source):
        def open(self):
            raise OSError("Failed to open")

    source = FailedSource()
    with pytest.raises(OSError), Tracker(backend=source):
        pass
    assert source.closed == 1


def test_demo_is_reproducible_and_tracker_can_reopen():
    tracker = Tracker.demo(realtime=False)
    with tracker:
        first = tracker.read()
        assert tracker.read().timestamp_us > first.timestamp_us
    with tracker:
        assert tracker.read() == first
    with pytest.raises(RuntimeError):
        tracker.read()


def test_disconnect_does_not_reuse_old_frame_and_reconnect_is_explicit():
    class Device:
        opens = 0
        closed = 0

        def open(self):
            self.opens += 1

        def read(self, timeout):
            if self.opens == 1:
                raise ConnectionError("Camera disconnected")
            return Frame(2, 200)

        def close(self):
            self.closed += 1

    device = Device()
    with Tracker(backend=device) as tracker:
        with pytest.raises(ConnectionError, match="Camera disconnected"):
            tracker.read()
        assert tracker.reconnect() is tracker
        assert tracker.read().id == 2
    assert device.opens == 2
    assert device.closed == 2


def test_frame_with_two_hands_selects_by_handedness():
    from dataclasses import replace

    with Tracker.demo(realtime=False) as tracker:
        right = tracker.read().right_hand
    left = replace(right, id=2, handedness="left")
    frame = Frame(1, 0, hands=(left, right))
    assert frame.right_hand is right
    assert frame.left_hand is left


def test_packed_x64_hand_layout_matches_sdk_contract():
    # Documented header contract, not sizeof() values derived from our declaration.
    assert C.sizeof(NativeHand) == 1084
    assert NativeHand.palm.offset == 40
    assert NativeHand.digits.offset == 120
    assert NativeHand.arm.offset == 1040
