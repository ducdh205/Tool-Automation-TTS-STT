"""Tie a child process's lifetime to this process on Windows.

Closing the tool's console window kills Python without running cleanup, which would
leave wyoming running and holding its port. A job object with KILL_ON_JOB_CLOSE ends
the child when the last handle to the job (held by this process) goes away.
"""

from __future__ import annotations

import ctypes
import logging
import os
import subprocess
from ctypes import wintypes

_LOG = logging.getLogger(__name__)

_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
    )]


class _BasicLimit(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _ExtendedLimit(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimit),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


_job: int | None = None


def _kill_on_close_job() -> int | None:
    global _job
    if _job is None:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        job = k32.CreateJobObjectW(None, None)
        if not job:
            return None
        info = _ExtendedLimit()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k32.SetInformationJobObject(wintypes.HANDLE(job), _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                                           ctypes.byref(info), ctypes.sizeof(info)):
            k32.CloseHandle(wintypes.HANDLE(job))
            return None
        _job = job  # never closed: the OS closes it when this process exits
    return _job


def kill_with_this_process(proc: subprocess.Popen) -> bool:
    """Best effort: True when ``proc`` will die together with this process."""
    if os.name != "nt":
        return False
    try:
        job = _kill_on_close_job()
        if job is None:
            return False
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        return bool(k32.AssignProcessToJobObject(wintypes.HANDLE(job), wintypes.HANDLE(int(proc._handle))))  # type: ignore[attr-defined]
    except (OSError, AttributeError) as e:
        _LOG.debug("job object unavailable: %s", e)
        return False
