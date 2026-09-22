from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass
from typing import Any

JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


class JobObjectError(RuntimeError):
    """Stable, non-sensitive failure raised by the Windows resource boundary."""

    def __init__(self, code: str, message: str = "解析资源限制不可用。") -> None:
        super().__init__(message)
        self.code = code


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


@dataclass(frozen=True)
class ResourceLimitCapabilities:
    platform: str
    job_object_supported: bool
    memory_limit_bytes: int


class ManagedJobObject:
    """A small ctypes wrapper with deterministic handle ownership.

    On non-Windows platforms the object is an explicit compatibility path. It
    keeps the parser API identical but does not claim to enforce a hard limit.
    """

    def __init__(self, handle: int | None, memory_limit_bytes: int) -> None:
        self._handle = handle
        self.memory_limit_bytes = memory_limit_bytes

    @property
    def supported(self) -> bool:
        return self._handle is not None

    @classmethod
    def create(cls, memory_limit_bytes: int) -> ManagedJobObject:
        if memory_limit_bytes <= 0:
            raise JobObjectError("JOB_OBJECT_LIMIT_INVALID")
        if os.name != "nt":
            return cls(None, memory_limit_bytes)

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            wintypes.INT,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise JobObjectError("JOB_OBJECT_CREATE_FAILED")

        info = _ExtendedLimitInformation()
        info.BasicLimitInformation.LimitFlags = (
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_PROCESS_MEMORY
        )
        info.ProcessMemoryLimit = memory_limit_bytes
        ok = kernel32.SetInformationJobObject(
            handle,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            kernel32.CloseHandle(handle)
            raise JobObjectError("JOB_OBJECT_LIMIT_CONFIG_FAILED")
        return cls(int(handle), memory_limit_bytes)

    def assign(self, process: Any) -> None:
        if not self.supported:
            return
        handle = getattr(process, "_handle", None)
        if handle is None:
            raise JobObjectError("JOB_OBJECT_ASSIGN_FAILED")
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        if not kernel32.AssignProcessToJobObject(self._handle, int(handle)):
            raise JobObjectError("JOB_OBJECT_ASSIGN_FAILED")

    def close(self) -> None:
        handle = self._handle
        self._handle = None
        if handle is None or os.name != "nt":
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CloseHandle(handle)

    def __enter__(self) -> ManagedJobObject:
        return self

    def __exit__(self, _exc_type: Any, _exc_value: Any, _traceback: Any) -> None:
        self.close()


def resource_limit_capabilities(memory_limit_bytes: int) -> ResourceLimitCapabilities:
    return ResourceLimitCapabilities(
        platform=os.name,
        job_object_supported=os.name == "nt",
        memory_limit_bytes=memory_limit_bytes,
    )
