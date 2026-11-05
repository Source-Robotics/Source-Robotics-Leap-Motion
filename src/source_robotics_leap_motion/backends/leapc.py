"""Synchronous LeapC polling. Every returned frame owns all of its data."""

from __future__ import annotations

import ctypes as C
import math
import os
import struct
import sys
import time

from ..errors import ConnectionError, RuntimeNotFoundError
from ..models import Bone, Finger, Frame, Hand, Palm, Quaternion, Vector3
from ..runtime import find_library
from ._native import NativeHand, NativeMessage, NativeTrackingEvent

TIMEOUT = 0xE2010004
CONNECTION = 1
CONNECTION_LOST = 2
DEVICE = 3
DEVICE_FAILURE = 4
TRACKING = 0x100
DEVICE_LOST = 0x104


def _vector(value, scale: float = 1.0) -> Vector3:
    return Vector3(value.x * scale, value.y * scale, value.z * scale)


def _quaternion(value) -> Quaternion:
    norm = math.sqrt(value.x**2 + value.y**2 + value.z**2 + value.w**2)
    if not math.isfinite(norm) or norm < 1e-8:
        raise ValueError("Invalid rotation in native tracking frame")
    return Quaternion(value.x / norm, value.y / norm, value.z / norm, value.w / norm)


def _bone(value) -> Bone:
    return Bone(
        _vector(value.prev_joint, 0.001),
        _vector(value.next_joint, 0.001),
        value.width * 0.001,
        _quaternion(value.rotation),
    )


def copy_hand(value: NativeHand) -> Hand:
    if value.type not in (0, 1):
        raise ValueError(f"Unexpected native hand type: {value.type}")
    palm = value.palm
    fingers = tuple(
        Finger(
            id=digit.finger_id,
            name=name,
            bones=tuple(_bone(bone) for bone in digit.bones),
            extended=bool(digit.is_extended),
        )
        for name, digit in zip(
            ("thumb", "index", "middle", "ring", "pinky"), value.digits, strict=True
        )
    )
    return Hand(
        id=value.id,
        handedness="left" if value.type == 0 else "right",
        palm=Palm(
            position=_vector(palm.position, 0.001),
            orientation=_quaternion(palm.orientation),
            velocity=_vector(palm.velocity, 0.001),
            normal=_vector(palm.normal),
            direction=_vector(palm.direction),
            width=palm.width * 0.001,
        ),
        grab_strength=value.grab_strength,
        pinch_strength=value.pinch_strength,
        pinch_distance=value.pinch_distance * 0.001,
        visible_time_us=value.visible_time,
        fingers=fingers,
        arm=_bone(value.arm),
    )


def copy_frame(event: NativeTrackingEvent, device_id: int) -> Frame:
    if event.nHands > 16 or (event.nHands and not event.pHands):
        raise ValueError("Invalid native tracking hand array")
    return Frame(
        id=event.tracking_frame_id,
        timestamp_us=event.info.timestamp,
        hands=tuple(copy_hand(event.pHands[index]) for index in range(event.nHands)),
        framerate=event.framerate,
        device_id=device_id,
    )


class LeapCBackend:
    name = "leapc"

    def __init__(self, library_path: str | None = None, *, connect_timeout: float = 5.0):
        self.library_path = library_path
        self.connect_timeout = connect_timeout
        self._dll = None
        self._directory = None
        self._handle = C.c_void_p()
        self._connected = False

    def _check(self, result: int, operation: str) -> None:
        if result:
            raise ConnectionError(f"LeapC {operation} failed (0x{result:08X})")

    def open(self) -> None:
        if sys.platform not in ("win32", "linux", "darwin") or struct.calcsize("P") != 8:
            raise RuntimeNotFoundError(
                "Native LeapC tracking requires 64-bit Windows, Linux, or macOS"
            )
        path = find_library(self.library_path)
        try:
            if sys.platform == "win32":
                self._directory = os.add_dll_directory(str(path.parent))
                self._dll = C.WinDLL(str(path))
            else:
                self._dll = C.CDLL(str(path))
            signatures = {
                "LeapCreateConnection": ([C.c_void_p, C.POINTER(C.c_void_p)], C.c_uint32),
                "LeapOpenConnection": ([C.c_void_p], C.c_uint32),
                "LeapSetPolicyFlags": ([C.c_void_p, C.c_uint64, C.c_uint64], C.c_uint32),
                "LeapPollConnection": (
                    [C.c_void_p, C.c_uint32, C.POINTER(NativeMessage)],
                    C.c_uint32,
                ),
                "LeapCloseConnection": ([C.c_void_p], None),
                "LeapDestroyConnection": ([C.c_void_p], None),
            }
            for name, (args, result) in signatures.items():
                function = getattr(self._dll, name)
                function.argtypes = args
                function.restype = result
        except (OSError, AttributeError) as exc:
            self.close()
            raise RuntimeNotFoundError(f"Cannot load compatible LeapC at {path}: {exc}") from exc
        try:
            self._check(self._dll.LeapCreateConnection(None, C.byref(self._handle)), "create")
            self._check(self._dll.LeapOpenConnection(self._handle), "open")
            end = time.perf_counter() + self.connect_timeout
            while not self._connected and (remaining := end - time.perf_counter()) > 0:
                self._poll(min(remaining, 0.1))
            if not self._connected:
                raise ConnectionError(
                    "LeapC loaded, but the tracking service did not connect. "
                    "The installed legacy 3.x service may need a compatible runtime update. "
                    "Run 'source-leap doctor' for details."
                )
            self._check(self._dll.LeapSetPolicyFlags(self._handle, 1, 0), "background policy")
        except BaseException:
            self.close()
            raise

    def _poll(self, timeout: float) -> Frame | None:
        message = NativeMessage()
        message.size = C.sizeof(message)
        result = self._dll.LeapPollConnection(
            self._handle, max(1, math.ceil(timeout * 1000)), C.byref(message)
        )
        if result == TIMEOUT:
            return None
        self._check(result, "poll")
        if message.type == CONNECTION:
            self._connected = True
        elif message.type == CONNECTION_LOST:
            self._connected = False
            raise ConnectionError("Connection to the tracking service was lost")
        elif message.type in (DEVICE_LOST, DEVICE_FAILURE):
            raise ConnectionError("Tracking camera disconnected or reported a device failure")
        elif message.type == TRACKING:
            if not message.pointer:
                raise ConnectionError("LeapC returned an empty tracking-event pointer")
            event = C.cast(message.pointer, C.POINTER(NativeTrackingEvent)).contents
            try:
                return copy_frame(event, message.device_id)
            except ValueError as exc:
                raise ConnectionError(f"Rejected invalid native frame: {exc}") from exc
        return None

    def read(self, timeout: float) -> Frame | None:
        if not self._handle.value:
            raise RuntimeError("Native connection is not open")
        end = time.perf_counter() + timeout
        while (remaining := end - time.perf_counter()) > 0:
            if (frame := self._poll(min(remaining, 0.1))) is not None:
                return frame
        return None

    def close(self) -> None:
        try:
            if self._dll is not None and self._handle.value:
                try:
                    self._dll.LeapCloseConnection(self._handle)
                finally:
                    self._dll.LeapDestroyConnection(self._handle)
        finally:
            self._handle = C.c_void_p()
            self._connected = False
            if self._directory is not None:
                self._directory.close()
                self._directory = None
