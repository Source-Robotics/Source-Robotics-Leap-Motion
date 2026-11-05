"""Windows job ownership: closing our handle ends only our private process tree."""

import ctypes as C
from ctypes import wintypes as W


class BasicLimits(C.Structure):
    _fields_ = [
        ("process_time", C.c_int64),
        ("job_time", C.c_int64),
        ("flags", W.DWORD),
        ("minimum_working_set", C.c_size_t),
        ("maximum_working_set", C.c_size_t),
        ("active_process_limit", W.DWORD),
        ("affinity", C.c_size_t),
        ("priority_class", W.DWORD),
        ("scheduling_class", W.DWORD),
    ]


class IOAccounting(C.Structure):
    _fields_ = [
        (name, C.c_uint64)
        for name in (
            "read_operations",
            "write_operations",
            "other_operations",
            "read_bytes",
            "write_bytes",
            "other_bytes",
        )
    ]


class ExtendedLimits(C.Structure):
    _fields_ = [
        ("basic", BasicLimits),
        ("io", IOAccounting),
        ("process_memory", C.c_size_t),
        ("job_memory", C.c_size_t),
        ("peak_process_memory", C.c_size_t),
        ("peak_job_memory", C.c_size_t),
    ]


class ProcessJob:
    def __init__(self):
        self._kernel = C.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": ([C.c_void_p, W.LPCWSTR], W.HANDLE),
            "SetInformationJobObject": ([W.HANDLE, C.c_int, C.c_void_p, W.DWORD], W.BOOL),
            "OpenProcess": ([W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
            "AssignProcessToJobObject": ([W.HANDLE, W.HANDLE], W.BOOL),
            "CloseHandle": ([W.HANDLE], W.BOOL),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self._kernel, name)
            function.argtypes = arguments
            function.restype = result
        self._handle = self._kernel.CreateJobObjectW(None, None)
        if not self._handle:
            raise C.WinError(C.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self._kernel.SetInformationJobObject(
            self._handle, 9, C.byref(limits), C.sizeof(limits)
        ):
            error = C.WinError(C.get_last_error())
            self.close()
            raise error

    def assign(self, pid: int) -> None:
        process = self._kernel.OpenProcess(0x0101, False, pid)  # SET_QUOTA | TERMINATE
        if not process:
            raise C.WinError(C.get_last_error())
        try:
            if not self._kernel.AssignProcessToJobObject(self._handle, process):
                raise C.WinError(C.get_last_error())
        finally:
            self._kernel.CloseHandle(process)

    def close(self) -> None:
        if self._handle:
            self._kernel.CloseHandle(self._handle)
            self._handle = None
