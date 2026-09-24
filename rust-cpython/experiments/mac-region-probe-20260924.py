"""Bounded, read-only libproc region probe for one controlled macOS child.

This is a feasibility diagnostic. It deliberately refuses to publish a region
sum when the public address walk encounters a submap or an ambiguous return.
"""

import ctypes
import json
import mmap
import platform
import resource
import subprocess
import sys
import time


PROC_PIDREGIONINFO = 7
PROC_PIDTASKINFO = 4
PROC_REGION_SUBMAP = 1
MAX_REGIONS = 4096
ALLOCATION = 32 * 1024 * 1024


class Region(ctypes.Structure):
    _fields_ = [
        ("protection", ctypes.c_uint32),
        ("max_protection", ctypes.c_uint32),
        ("inheritance", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("offset", ctypes.c_uint64),
        ("behavior", ctypes.c_uint32),
        ("wired", ctypes.c_uint32),
        ("tag", ctypes.c_uint32),
        ("resident", ctypes.c_uint32),
        ("cow_private", ctypes.c_uint32),
        ("swapped", ctypes.c_uint32),
        ("dirtied", ctypes.c_uint32),
        ("references", ctypes.c_uint32),
        ("shadow_depth", ctypes.c_uint32),
        ("share_mode", ctypes.c_uint32),
        ("private", ctypes.c_uint32),
        ("shared", ctypes.c_uint32),
        ("object_id", ctypes.c_uint32),
        ("depth", ctypes.c_uint32),
        ("address", ctypes.c_uint64),
        ("size", ctypes.c_uint64),
    ]


class Task(ctypes.Structure):
    _fields_ = [("virtual_size", ctypes.c_uint64),
                ("resident_size", ctypes.c_uint64),
                ("total_user", ctypes.c_uint64),
                ("total_system", ctypes.c_uint64),
                ("threads_user", ctypes.c_uint64),
                ("threads_system", ctypes.c_uint64),
                ("policy", ctypes.c_int32), ("faults", ctypes.c_int32),
                ("pageins", ctypes.c_int32), ("cow_faults", ctypes.c_int32),
                ("messages_sent", ctypes.c_int32),
                ("messages_received", ctypes.c_int32),
                ("syscalls_mach", ctypes.c_int32),
                ("syscalls_unix", ctypes.c_int32),
                ("context_switches", ctypes.c_int32),
                ("thread_count", ctypes.c_int32),
                ("running_threads", ctypes.c_int32),
                ("priority", ctypes.c_int32)]


def child():
    anonymous = None
    while True:
        command = sys.stdin.readline().strip()
        if command == "exit" or not command:
            return
        if command == "reserve":
            anonymous = mmap.mmap(-1, ALLOCATION)
        elif command == "touch":
            for offset in range(0, ALLOCATION, mmap.PAGESIZE):
                anonymous[offset] = 1
        elif command != "idle":
            raise ValueError(command)
        print("ready", flush=True)


def scan(libproc, pid):
    start = time.perf_counter_ns()
    address = 0
    counts = {"full": 0, "zero": 0, "short": 0, "error": 0}
    totals = {"resident": 0, "private": 0, "shared": 0}
    submaps = 0
    alias_modes = 0
    failure = None
    for _ in range(MAX_REGIONS):
        region = Region()
        ctypes.set_errno(0)
        result = libproc.proc_pidinfo(pid, PROC_PIDREGIONINFO, address,
                                      ctypes.byref(region), ctypes.sizeof(region))
        if result == 0:
            counts["zero"] += 1
            failure = f"zero return at {address:#x}, errno={ctypes.get_errno()}"
            break
        if result < 0:
            counts["error"] += 1
            failure = f"error at {address:#x}, errno={ctypes.get_errno()}"
            break
        if result != ctypes.sizeof(region):
            counts["short"] += 1
            failure = f"short return {result} at {address:#x}"
            break
        counts["full"] += 1
        if region.address < address or region.size == 0:
            failure = f"nonprogressing region at {address:#x}"
            break
        next_address = region.address + region.size
        if next_address <= address or next_address > (1 << 64) - 1:
            failure = f"address overflow at {address:#x}"
            break
        submaps += bool(region.flags & PROC_REGION_SUBMAP)
        alias_modes += region.share_mode in (6, 7)
        totals["resident"] += region.resident
        totals["private"] += region.private
        totals["shared"] += region.shared
        address = next_address
    else:
        failure = f"region cap {MAX_REGIONS} reached"
    return {"regions": counts["full"], "returns": counts,
            "submaps": submaps, "alias_modes": alias_modes,
            "page_totals_unqualified": totals, "failure": failure,
            "elapsed_ms": (time.perf_counter_ns() - start) / 1e6}


def main():
    if sys.platform != "darwin":
        raise SystemExit("macOS only")
    libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    libproc.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int,
                                     ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
    libproc.proc_pidinfo.restype = ctypes.c_int
    child_process = subprocess.Popen([sys.executable, __file__, "child"],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     text=True)
    try:
        output = {"pid": child_process.pid, "macos": platform.mac_ver()[0],
                  "page_size": mmap.PAGESIZE,
                  "region_struct_size": ctypes.sizeof(Region), "states": {}}
        for state in ("idle", "reserve", "touch"):
            child_process.stdin.write(state + "\n")
            child_process.stdin.flush()
            if child_process.stdout.readline().strip() != "ready":
                raise RuntimeError("child did not acknowledge checkpoint")
            task = Task()
            task_return = libproc.proc_pidinfo(child_process.pid, PROC_PIDTASKINFO,
                                               0, ctypes.byref(task), ctypes.sizeof(task))
            output["states"][state] = {"task_return": task_return,
                                        "rss_bytes": task.resident_size if task_return == ctypes.sizeof(task) else None,
                                        "scan": scan(libproc, child_process.pid)}
        output["observer_max_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        print(json.dumps(output, indent=2))
    finally:
        child_process.stdin.write("exit\n")
        child_process.stdin.flush()
        child_process.wait(timeout=5)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "child":
        child()
    else:
        main()
