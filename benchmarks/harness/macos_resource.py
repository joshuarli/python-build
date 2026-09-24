"""Read one macOS process's kernel memory counters without instrumenting it.

`proc_pid_rusage` accepts a live or zombie PID. Its lifetime footprint peak
survives process exit only until the parent reaps that PID. These counters are
per process: summing lifetime peaks does not give a simultaneous tree peak.
Physical footprint is Apple's kernel ledger of dirty memory owned by a
process. It can include charges outside the process's mappings and is neither
Linux USS nor PSS; its definition is subject to OS changes (`footprint(1)`).
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
import errno
from functools import lru_cache
import sys


_RUSAGE_INFO_V4 = 4
_PROC_PGRP_ONLY = 2
_PROC_PPID_ONLY = 6
_PROC_PIDTASKALLINFO = 2
_SZOMB = 5
_MAXCOMLEN = 16

# Exact SDK layout of struct rusage_info_v4 from <sys/resource.h>. A shorter
# buffer would let libproc overwrite Python-owned memory, even when only the
# first few fields are read. All fields are uint64_t after the 16-byte UUID.
_V4_FIELDS = (
    "ri_user_time", "ri_system_time", "ri_pkg_idle_wkups",
    "ri_interrupt_wkups", "ri_pageins", "ri_wired_size",
    "ri_resident_size", "ri_phys_footprint", "ri_proc_start_abstime",
    "ri_proc_exit_abstime", "ri_child_user_time", "ri_child_system_time",
    "ri_child_pkg_idle_wkups", "ri_child_interrupt_wkups", "ri_child_pageins",
    "ri_child_elapsed_abstime", "ri_diskio_bytesread", "ri_diskio_byteswritten",
    "ri_cpu_time_qos_default", "ri_cpu_time_qos_maintenance",
    "ri_cpu_time_qos_background", "ri_cpu_time_qos_utility",
    "ri_cpu_time_qos_legacy", "ri_cpu_time_qos_user_initiated",
    "ri_cpu_time_qos_user_interactive", "ri_billed_system_time",
    "ri_serviced_system_time", "ri_logical_writes",
    "ri_lifetime_max_phys_footprint", "ri_instructions", "ri_cycles",
    "ri_billed_energy", "ri_serviced_energy",
    "ri_interval_max_phys_footprint", "ri_runnable_time",
)


class _RUsageInfoV4(ctypes.Structure):
    _fields_ = [("ri_uuid", ctypes.c_uint8 * 16)] + [
        (name, ctypes.c_uint64) for name in _V4_FIELDS
    ]


# Layouts from the installed macOS SDK's <sys/proc_info.h>. The full structs
# are required: proc_pidinfo writes sizeof(struct proc_taskallinfo) bytes.
class _ProcBsdInfo(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_uint32) for name in (
            "pbi_flags", "pbi_status", "pbi_xstatus", "pbi_pid", "pbi_ppid",
            "pbi_uid", "pbi_gid", "pbi_ruid", "pbi_rgid", "pbi_svuid",
            "pbi_svgid", "rfu_1",
        )
    ] + [
        ("pbi_comm", ctypes.c_char * _MAXCOMLEN),
        ("pbi_name", ctypes.c_char * (2 * _MAXCOMLEN)),
    ] + [
        (name, ctypes.c_uint32) for name in (
            "pbi_nfiles", "pbi_pgid", "pbi_pjobc", "e_tdev", "e_tpgid",
        )
    ] + [
        ("pbi_nice", ctypes.c_int32),
        ("pbi_start_tvsec", ctypes.c_uint64),
        ("pbi_start_tvusec", ctypes.c_uint64),
    ]


class _ProcTaskInfo(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in (
        "pti_virtual_size", "pti_resident_size", "pti_total_user",
        "pti_total_system", "pti_threads_user", "pti_threads_system",
    )] + [(name, ctypes.c_int32) for name in (
        "pti_policy", "pti_faults", "pti_pageins", "pti_cow_faults",
        "pti_messages_sent", "pti_messages_received", "pti_syscalls_mach",
        "pti_syscalls_unix", "pti_csw", "pti_threadnum", "pti_numrunning",
        "pti_priority",
    )]


class _ProcTaskAllInfo(ctypes.Structure):
    _fields_ = [("pbsd", _ProcBsdInfo), ("ptinfo", _ProcTaskInfo)]


@dataclass(frozen=True)
class MacProcessInfo:
    parent_pid: int
    process_group: int
    resident_bytes: int
    start_time: tuple[int, int]


@lru_cache(maxsize=1)
def _process_functions() -> tuple[ctypes._CFuncPtr, ctypes._CFuncPtr]:
    if sys.platform != "darwin":
        raise RuntimeError("macOS process table requires Darwin")
    try:
        library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    except OSError as error:
        raise RuntimeError("macOS libproc is unavailable") from error
    listpids = library.proc_listpids
    listpids.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_int]
    listpids.restype = ctypes.c_int
    pidinfo = library.proc_pidinfo
    pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                        ctypes.c_void_p, ctypes.c_int]
    pidinfo.restype = ctypes.c_int
    return listpids, pidinfo


def _listed_pids(kind: int, identifier: int) -> set[int]:
    listpids, _ = _process_functions()
    size = listpids(kind, identifier, None, 0)
    if size < 0:
        raise OSError(ctypes.get_errno() or errno.EIO, "proc_listpids size failed")
    capacity = max(1024, size + 1024) // ctypes.sizeof(ctypes.c_int)
    while True:
        buffer = (ctypes.c_int * capacity)()
        count_bytes = listpids(kind, identifier, buffer, ctypes.sizeof(buffer))
        if count_bytes < 0:
            raise OSError(ctypes.get_errno() or errno.EIO, "proc_listpids failed")
        if count_bytes < ctypes.sizeof(buffer):
            return {pid for pid in buffer[:count_bytes // ctypes.sizeof(ctypes.c_int)]
                    if pid > 0}
        capacity *= 2
        if capacity > 262144:
            raise RuntimeError("macOS process list exceeded 1 MiB")


def read_process_table(root_pid: int, process_group: int) -> dict[int, MacProcessInfo]:
    """Read group members and recursively discover descendants via libproc."""
    _, pidinfo = _process_functions()
    pending = _listed_pids(_PROC_PGRP_ONLY, process_group) | {root_pid}
    table: dict[int, MacProcessInfo] = {}
    visited: set[int] = set()
    while pending:
        pid = pending.pop()
        if pid in visited:
            continue
        visited.add(pid)
        info = _ProcTaskAllInfo()
        ctypes.set_errno(0)
        size = pidinfo(pid, _PROC_PIDTASKALLINFO, 0, ctypes.byref(info), ctypes.sizeof(info))
        if size != ctypes.sizeof(info):
            # An exited process can vanish between listing and this read.
            code = ctypes.get_errno()
            if code not in (0, errno.ESRCH, errno.ENOENT):
                raise OSError(code, f"proc_pidinfo failed for pid {pid}")
            continue
        bsd = info.pbsd
        if bsd.pbi_pid != pid or bsd.pbi_status == _SZOMB:
            continue
        table[pid] = MacProcessInfo(
            parent_pid=bsd.pbi_ppid,
            process_group=bsd.pbi_pgid,
            resident_bytes=info.ptinfo.pti_resident_size,
            start_time=(bsd.pbi_start_tvsec, bsd.pbi_start_tvusec),
        )
        pending.update(_listed_pids(_PROC_PPID_ONLY, pid) - visited)
    return table


@dataclass(frozen=True)
class MacProcessMemory:
    """Byte counts for one PID; absolute times identify birth and exit."""

    resident_bytes: int
    phys_footprint_bytes: int
    lifetime_max_phys_footprint_bytes: int
    start_abstime: int
    exit_abstime: int


@lru_cache(maxsize=1)
def _proc_pid_rusage() -> ctypes._CFuncPtr:
    if sys.platform != "darwin":
        raise RuntimeError("macOS process resource counters require Darwin")
    try:
        library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    except OSError as error:
        raise RuntimeError("macOS libproc is unavailable") from error
    function = library.proc_pid_rusage
    function.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
    function.restype = ctypes.c_int
    return function


def read_process_memory(pid: int) -> MacProcessMemory:
    """Read current RSS/footprint and kernel-recorded lifetime footprint peak.

    The current values describe only this PID at the read instant; after exit
    the zombie's current footprint may be zero. The lifetime peak remains
    available until reap. A vanished PID raises ``ProcessLookupError``.
    """

    if pid <= 0:
        raise ValueError("pid must be positive")
    info = _RUsageInfoV4()
    ctypes.set_errno(0)
    if _proc_pid_rusage()(pid, _RUSAGE_INFO_V4, ctypes.byref(info)) != 0:
        code = ctypes.get_errno() or errno.EIO
        raise OSError(code, f"proc_pid_rusage failed for pid {pid}")
    return MacProcessMemory(
        resident_bytes=info.ri_resident_size,
        phys_footprint_bytes=info.ri_phys_footprint,
        lifetime_max_phys_footprint_bytes=info.ri_lifetime_max_phys_footprint,
        start_abstime=info.ri_proc_start_abstime,
        exit_abstime=info.ri_proc_exit_abstime,
    )
