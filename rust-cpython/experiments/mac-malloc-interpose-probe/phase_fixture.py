"""Bounded parent and spawn-child diagnostic for the experiment observer."""

import ctypes
import multiprocessing
import os
import resource
import sys
import threading


def exercise(role: str, size: int, count: int, threads: int = 0) -> None:
    observer = ctypes.CDLL(os.environ["DYLD_INSERT_LIBRARIES"])
    libc = ctypes.CDLL(None)
    libc.malloc.argtypes = (ctypes.c_size_t,)
    libc.malloc.restype = ctypes.c_void_p
    libc.free.argtypes = (ctypes.c_void_p,)
    observer.malloc_observer_phase_begin.restype = ctypes.c_int
    observer.malloc_observer_phase_end.restype = ctypes.c_int

    def batch(n: int) -> None:
        for _ in range(n):
            pointer = libc.malloc(size)
            if not pointer:
                raise MemoryError(size)
            libc.free(pointer)

    batch(3)
    if observer.malloc_observer_phase_begin() != 1:
        raise RuntimeError("phase begin rejected")
    batch(count)
    workers = [threading.Thread(target=batch, args=(10,)) for _ in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    if observer.malloc_observer_phase_end() != 1:
        raise RuntimeError("phase end rejected")
    batch(3)
    print(f"MARK role={role} pid={os.getpid()} size={size} expected={count + threads * 10}", flush=True)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    print(
        f"USAGE role={role} pid={os.getpid()} user={usage.ru_utime:.6f} "
        f"system={usage.ru_stime:.6f} maxrss_bytes={usage.ru_maxrss}",
        flush=True,
    )


def child() -> None:
    exercise("child", 73729, 9)


if __name__ == "__main__":
    print(f"START pid={os.getpid()} executable={sys.executable}", flush=True)
    exercise("parent", 65537, 7, 4)
    process = multiprocessing.get_context("spawn").Process(target=child)
    process.start()
    process.join(10)
    if process.is_alive():
        process.kill()
        process.join()
        raise TimeoutError("spawn child exceeded 10 seconds")
    if process.exitcode:
        raise RuntimeError(f"spawn child exited {process.exitcode}")
