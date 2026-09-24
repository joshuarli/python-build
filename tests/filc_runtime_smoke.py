"""Focused behavior smoke for the installed Fil-C CPython interpreter.

Run against a copied or extracted distribution, never the build-tree Python.
The larger native-module, TLS, multiprocessing, and CPython regression probes
live in ``buildsys.validate_filc`` and ``buildsys.testsuite``.
"""

from __future__ import annotations

import asyncio
import ctypes
import errno
import faulthandler
import gc
import json
import math
import mmap
import os
import signal
import socket
import subprocess
import sys
import sysconfig
import tempfile
import threading


def _generator():
    for value in range(4):
        yield value * value


async def _coroutine():
    await asyncio.sleep(0)
    return 42


def main() -> None:
    assert sys.version_info[:3] == (3, 14, 6)
    assert sys._base_executable == sys.executable
    assert sys.orig_argv[0] == sys.executable
    assert int(sysconfig.get_config_var("ALIGNOF_MAX_ALIGN_T")) >= ctypes.alignment(ctypes.c_longdouble)
    import resource
    assert not hasattr(resource, "prlimit")
    assert not hasattr(socket, "sethostname")
    assert not hasattr(socket, "AF_RDS")
    assert not hasattr(socket, "PF_RDS")
    assert not hasattr(signal, "pthread_kill")
    assert not hasattr(signal, "pidfd_send_signal")
    assert not hasattr(__import__("time"), "clock_settime")
    assert not hasattr(__import__("time"), "pthread_getcpuclockid")
    assert not hasattr(os, "unshare")
    assert not hasattr(os, "setns")
    assert subprocess.check_output(
        [sys._base_executable, "-c", "print(7)"], text=True,
    ).strip() == "7"
    odd_environment = dict(os.environ)
    odd_environment["not-a-shell-name"] = "42"
    assert subprocess.check_output(
        [sys.executable, "-c", "import os; print(os.environ['not-a-shell-name'])"],
        env=odd_environment, text=True,
    ).strip() == "42"
    try:
        faulthandler.enable()
    except RuntimeError as error:
        assert error.args[0] == errno.ENOSYS, error
    else:
        raise AssertionError("Fil-C unexpectedly accepted fatal signal handlers")
    assert not faulthandler.is_enabled()
    faulthandler.register(signal.SIGUSR1)
    assert faulthandler.unregister(signal.SIGUSR1)
    faulthandler_cli = subprocess.run(
        [sys.executable, "-X", "faulthandler", "-c",
         "import faulthandler; print(faulthandler.is_enabled())"],
        capture_output=True, text=True,
    )
    assert faulthandler_cli.returncode == 0, faulthandler_cli.stderr
    assert faulthandler_cli.stdout.strip() == "False"
    with tempfile.TemporaryFile(mode="w+t") as output:
        faulthandler.dump_traceback(file=output, all_threads=True)
        output.seek(0)
        assert "most recent call first" in output.read()
    try:
        raise ValueError("filc")
    except ValueError as error:
        assert str(error) == "filc"

    assert 2**4096 >> 4095 == 2
    assert math.copysign(1.0, math.fma(1e-300, -1e-300, 0.0)) == -1.0
    assert sum(_generator()) == 14
    assert asyncio.run(_coroutine()) == 42

    def recurse(depth: int) -> int:
        return 0 if depth == 0 else 1 + recurse(depth - 1)

    assert recurse(400) == 400
    cyclic = []
    cyclic.append(cyclic)
    del cyclic
    assert gc.collect() >= 1

    lock = threading.Lock()
    total = [0]

    def worker() -> None:
        for _ in range(200):
            with lock:
                total[0] += 1

    workers = [threading.Thread(target=worker) for _ in range(4)]
    for thread in workers:
        thread.start()
    for thread in workers:
        thread.join(timeout=10)
        assert not thread.is_alive()
    assert total == [800]

    delivered = []
    previous = signal.signal(signal.SIGUSR1, lambda signum, frame: delivered.append(signum))
    try:
        os.kill(os.getpid(), signal.SIGUSR1)
        assert delivered == [signal.SIGUSR1]
    finally:
        signal.signal(signal.SIGUSR1, previous)

    assert subprocess.check_output([sys.executable, "-c", "print(42)"], text=True).strip() == "42"
    with mmap.mmap(-1, 4096) as shared:
        shared[:4] = b"filc"
        assert shared[:4] == b"filc"
    left, right = socket.socketpair()
    try:
        left.sendall(b"filc")
        assert right.recv(4) == b"filc"
    finally:
        left.close()
        right.close()

    print(json.dumps({"ok": True, "version": list(sys.version_info[:3])}))


if __name__ == "__main__":
    main()
