"""Read one macOS process's kernel memory counters without instrumenting it.

`proc_pid_rusage` accepts a live or zombie PID. Its lifetime footprint peak
survives process exit only until the parent reaps that PID. These counters are
per process: summing lifetime peaks does not give a simultaneous tree peak.
Physical footprint is Apple's charged memory measure, not Linux USS or PSS.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
import errno
from functools import lru_cache
import sys


_RUSAGE_INFO_V4 = 4

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


@dataclass(frozen=True)
class MacProcessMemory:
    """Byte counts for one PID; ``start_abstime`` identifies PID reuse."""

    resident_bytes: int
    phys_footprint_bytes: int
    lifetime_max_phys_footprint_bytes: int
    start_abstime: int


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
    )
