"""Contract and live-process checks for macOS libproc memory counters."""

from __future__ import annotations

import ctypes
import errno
import os
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from benchmarks.harness import macos_resource


class MacResourceLayoutTests(unittest.TestCase):
    def test_v4_buffer_matches_sdk_layout(self):
        info = macos_resource._RUsageInfoV4
        self.assertEqual(macos_resource._RUSAGE_INFO_V4, 4)
        self.assertEqual(ctypes.sizeof(info), 296)
        self.assertEqual(info.ri_resident_size.offset, 64)
        self.assertEqual(info.ri_phys_footprint.offset, 72)
        self.assertEqual(info.ri_proc_start_abstime.offset, 80)
        self.assertEqual(info.ri_lifetime_max_phys_footprint.offset, 240)

    def test_invalid_pid_and_libproc_failure_are_not_reported_as_zero(self):
        with self.assertRaises(ValueError):
            macos_resource.read_process_memory(0)

        def unavailable(pid: int, flavor: int, buffer: object) -> int:
            ctypes.set_errno(errno.ESRCH)
            return -1

        with patch.object(macos_resource, "_proc_pid_rusage", return_value=unavailable):
            with self.assertRaises(ProcessLookupError):
                macos_resource.read_process_memory(123456)

    def test_non_macos_host_has_explicit_unavailable_error(self):
        with patch.object(macos_resource.sys, "platform", "linux"):
            macos_resource._proc_pid_rusage.cache_clear()
            with self.assertRaisesRegex(RuntimeError, "require Darwin"):
                macos_resource.read_process_memory(1)
        macos_resource._proc_pid_rusage.cache_clear()

    def test_missing_libproc_has_explicit_unavailable_error(self):
        with patch.object(macos_resource.sys, "platform", "darwin"):
            with patch.object(macos_resource.ctypes, "CDLL", side_effect=OSError("missing")):
                macos_resource._proc_pid_rusage.cache_clear()
                with self.assertRaisesRegex(RuntimeError, "libproc is unavailable"):
                    macos_resource.read_process_memory(1)
        macos_resource._proc_pid_rusage.cache_clear()


@unittest.skipUnless(sys.platform == "darwin", "macOS libproc")
class MacResourceProcessTests(unittest.TestCase):
    def test_live_and_zombie_process_preserve_lifetime_footprint(self):
        code = (
            "import sys; "
            "memory=bytearray(16*1024*1024); "
            "memory[::4096]=b'x'*len(memory[::4096]); "
            "print('ready', flush=True); sys.stdin.buffer.read(1)"
        )
        with subprocess.Popen(
            [sys.executable, "-c", code],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        ) as process:
            assert process.stdin is not None and process.stdout is not None
            self.assertEqual(process.stdout.readline(), b"ready\n")
            live = macos_resource.read_process_memory(process.pid)
            self.assertGreater(live.resident_bytes, 16 * 1024 * 1024)
            self.assertGreater(live.phys_footprint_bytes, 0)
            self.assertGreaterEqual(
                live.lifetime_max_phys_footprint_bytes, live.phys_footprint_bytes
            )

            process.stdin.close()
            deadline = time.monotonic() + 3
            while os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is None:
                self.assertLess(time.monotonic(), deadline, "child did not exit")
                time.sleep(0.005)
            zombie = macos_resource.read_process_memory(process.pid)
            self.assertEqual(zombie.start_abstime, live.start_abstime)
            self.assertGreaterEqual(
                zombie.lifetime_max_phys_footprint_bytes,
                live.lifetime_max_phys_footprint_bytes,
            )
        with self.assertRaises(ProcessLookupError):
            macos_resource.read_process_memory(process.pid)
