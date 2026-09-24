"""Short, deterministic allocation fixture for the macOS Allocations export probe."""

import ctypes
import mmap
import multiprocessing
import os
import sys
import time


def allocate(role: str, malloc_size: int, malloc_count: int, map_size: int) -> None:
    # Keep Python objects alive across the native batch so both kinds appear.
    objects = [bytearray(777) for _ in range(512)]
    libc = ctypes.CDLL(None)
    libc.malloc.argtypes = [ctypes.c_size_t]
    libc.malloc.restype = ctypes.c_void_p
    libc.free.argtypes = [ctypes.c_void_p]
    pointers = [libc.malloc(malloc_size) for _ in range(malloc_count)]
    if not all(pointers):
        raise MemoryError("controlled malloc batch")
    for pointer in pointers:
        libc.free(pointer)
    with mmap.mmap(-1, map_size) as mapping:
        for offset in range(0, map_size, mmap.PAGESIZE):
            mapping[offset] = 1
    print(
        f"MARK role={role} pid={os.getpid()} ppid={os.getppid()} "
        f"malloc_count={malloc_count} malloc_size={malloc_size} "
        f"mmap_size={map_size} python_objects={len(objects)}",
        flush=True,
    )
    time.sleep(0.5)


def child() -> None:
    allocate("spawn_child", 73729, 9, 5 * 1024 * 1024)


def main() -> None:
    print(f"START pid={os.getpid()} executable={sys.executable}", flush=True)
    allocate("parent", 65537, 7, 3 * 1024 * 1024)
    process = multiprocessing.get_context("spawn").Process(target=child)
    process.start()
    process.join(10)
    if process.is_alive():
        process.kill()
        process.join()
        raise TimeoutError("spawn child exceeded 10 seconds")
    if process.exitcode != 0:
        raise RuntimeError(f"spawn child exited {process.exitcode}")


if __name__ == "__main__":
    main()
