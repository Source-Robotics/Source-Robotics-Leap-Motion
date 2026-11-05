"""Internal LeapC declarations. Packed ABI; public objects never retain native memory.

Checked against Ultraleap's LeapC declarations. See docs/NATIVE_ABI.md.
"""

import ctypes as C


class Packed(C.Structure):
    _layout_ = "ms"
    _pack_ = 1


class NativeVector(Packed):
    _fields_ = [(axis, C.c_float) for axis in ("x", "y", "z")]


class NativeQuaternion(Packed):
    _fields_ = [(axis, C.c_float) for axis in ("x", "y", "z", "w")]


class NativeBone(Packed):
    _fields_ = [
        ("prev_joint", NativeVector),
        ("next_joint", NativeVector),
        ("width", C.c_float),
        ("rotation", NativeQuaternion),
    ]


class NativeDigit(Packed):
    _fields_ = [
        ("finger_id", C.c_int32),
        ("bones", NativeBone * 4),
        ("is_extended", C.c_uint32),
    ]


class NativePalm(Packed):
    _fields_ = [
        ("position", NativeVector),
        ("stabilized_position", NativeVector),
        ("velocity", NativeVector),
        ("normal", NativeVector),
        ("width", C.c_float),
        ("direction", NativeVector),
        ("orientation", NativeQuaternion),
    ]


class NativeHand(Packed):
    _fields_ = [
        ("id", C.c_uint32),
        ("flags", C.c_uint32),
        ("type", C.c_uint32),
        ("confidence", C.c_float),
        ("visible_time", C.c_uint64),
        ("pinch_distance", C.c_float),
        ("grab_angle", C.c_float),
        ("pinch_strength", C.c_float),
        ("grab_strength", C.c_float),
        ("palm", NativePalm),
        ("digits", NativeDigit * 5),
        ("arm", NativeBone),
    ]


class NativeFrameHeader(Packed):
    _fields_ = [
        ("reserved", C.c_void_p),
        ("frame_id", C.c_int64),
        ("timestamp", C.c_int64),
    ]


class NativeTrackingEvent(Packed):
    _fields_ = [
        ("info", NativeFrameHeader),
        ("tracking_frame_id", C.c_int64),
        ("nHands", C.c_uint32),
        ("pHands", C.POINTER(NativeHand)),
        ("framerate", C.c_float),
    ]


class NativeMessage(Packed):
    _fields_ = [
        ("size", C.c_uint32),
        ("type", C.c_uint32),
        ("pointer", C.c_void_p),
        ("device_id", C.c_uint32),
    ]
