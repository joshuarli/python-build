"""Sealed-execution profile and environment."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
import tempfile

from buildsys.sandbox import (
    SealedRun, available, describe, network_boundary_selftest,
)

DARWIN = sys.platform == "darwin"


class ProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_network_is_denied_by_the_profile(self) -> None:
        run = SealedRun(write_paths=[self.root / "out"], home=self.root / "home")
        self.assertIn("(deny network*)", run.profile())

    def test_every_write_path_becomes_a_rule(self) -> None:
        run = SealedRun(write_paths=[self.root / "a", self.root / "b"])
        profile = run.profile()
        for name in ("a", "b"):
            self.assertIn(f'(subpath "{(self.root / name).resolve()}")', profile)

    def test_posix_semaphores_are_permitted(self) -> None:
        # CPython's configure *executes* a sem_open probe. Denying it does not
        # fail the build: it silently defines POSIX_SEMAPHORES_NOT_ENABLED and
        # removes SemLock from _multiprocessing, so the sealed build would be
        # quietly worse than an unsealed one. This pins the allowance.
        run = SealedRun(write_paths=[self.root / "out"])
        self.assertIn("(allow ipc-posix-sem)", run.profile())

    def test_sem_open_actually_works_inside_the_profile(self) -> None:
        if not available():
            self.skipTest("sandbox-exec is not present")
        run = SealedRun(write_paths=[self.root / "out"], home=self.root / "home")
        # O_CREAT without O_EXCL, and an explicit unlink: a leaked named
        # semaphore makes the next run fail for a reason that has nothing to
        # do with the sandbox.
        code = (
            "import ctypes, os\n"
            "libc = ctypes.CDLL(None)\n"
            "libc.sem_open.restype = ctypes.c_void_p\n"
            "libc.sem_open.argtypes = [ctypes.c_char_p, ctypes.c_int]\n"
            "name = b'/pbsb_validation_probe'\n"
            "handle = libc.sem_open(name, os.O_CREAT, 0o600, 1)\n"
            "ok = handle != ctypes.c_void_p(-1).value\n"
            "if ok:\n"
            "    libc.sem_close(ctypes.c_void_p(handle))\n"
            "    libc.sem_unlink(name)\n"
            "print('SEM_OK' if ok else 'SEM_FAILED')\n"
        )
        result = run.run([sys.executable, "-c", code], cwd=self.root,
                         env=run.environment())
        self.assertIn("SEM_OK", result.stdout, result.stderr)

    def test_environment_is_an_allowlist_not_an_inheritance(self) -> None:
        run = SealedRun(write_paths=[self.root / "out"], home=self.root / "home")
        env = run.environment()
        for variable in ("PATH", "HOME", "LANG", "TZ", "TMPDIR"):
            self.assertIn(variable, env)
        # Variables that redirect a search path must not survive from the host.
        for variable in ("DYLD_LIBRARY_PATH", "PYTHONPATH", "SDKROOT", "CPATH"):
            self.assertNotIn(variable, env)

    def test_tmpdir_points_at_a_writable_declared_location(self) -> None:
        run = SealedRun(write_paths=[self.root / "out"], home=self.root / "home")
        run.prepare()
        self.assertTrue(Path(run.environment()["TMPDIR"]).is_dir())
        self.assertTrue(str(run.environment()["TMPDIR"]).startswith(str(self.root)))

    def test_prepare_creates_declared_directories(self) -> None:
        target = self.root / "nested" / "out"
        run = SealedRun(write_paths=[target], home=self.root / "home")
        run.prepare()
        self.assertTrue(target.is_dir())
        self.assertTrue((self.root / "home").is_dir())

    def test_describe_states_the_containment_is_weaker_than_a_container(self) -> None:
        # The report must describe the weaker macOS boundary without implying
        # equivalence with the Linux targets' container boundary.
        text = describe()
        self.assertEqual(text["mechanism"], "sandbox-exec")
        self.assertIn("weaker", text["isolation"])


@unittest.skipUnless(DARWIN, "sandbox-exec is macOS-only")
class BoundaryTests(unittest.TestCase):
    def test_network_boundary_is_enforced_not_merely_unexercised(self) -> None:
        if not available():
            self.skipTest("sandbox-exec is not present")
        with tempfile.TemporaryDirectory() as temporary:
            report = network_boundary_selftest(Path(sys.executable), Path(temporary))
        # The unsandboxed run must connect, otherwise the test would pass for
        # the wrong reason (no network at all) and prove nothing.
        self.assertTrue(report["unsandboxed_connected"])
        self.assertFalse(report["sandboxed_connected"])
        self.assertTrue(report["ok"])

    def test_sandboxed_writes_outside_declared_paths_are_refused(self) -> None:
        if not available():
            self.skipTest("sandbox-exec is not present")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "declared"
            root.mkdir()
            outside = Path(temporary) / "not-declared"
            run = SealedRun(write_paths=[root], home=root / "home")
            code = f"open({str(outside / 'x')!r}, 'w').write('nope')"
            result = run.run([sys.executable, "-c", code], cwd=root,
                             env=run.environment())
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((outside / "x").exists())


if __name__ == "__main__":
    unittest.main()
