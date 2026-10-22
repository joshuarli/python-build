from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from buildsys.product_process import product_environment, run_product_process


ROOT = Path(__file__).resolve().parents[1]
SCRATCH_ROOT = ROOT / ".work" / "tmp"


class ProductProcessTests(unittest.TestCase):
    def setUp(self) -> None:
        SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=SCRATCH_ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.install = self.root / "python"
        (self.install / "bin").mkdir(parents=True)
        self.cwd = self.root / "working directory"
        self.cwd.mkdir()

    def test_child_ignores_hostile_ambient_python_loader_and_homebrew_values(self) -> None:
        hostile_path = self.root / "injected"
        hostile_path.mkdir()
        (hostile_path / "product_process_injection.py").write_text("value = True\n")
        homebrew = self.root / "homebrew"
        (homebrew / "bin").mkdir(parents=True)
        inherited = {
            "PYTHONPATH": str(hostile_path),
            "PYTHONHOME": str(self.root / "invalid-python-home"),
            "PYTHONUSERBASE": str(self.root / "user-base"),
            "PYTHONNOUSERSITE": "0",
            "DYLD_LIBRARY_PATH": str(self.root / "dyld"),
            "DYLD_FRAMEWORK_PATH": str(self.root / "frameworks"),
            "LD_LIBRARY_PATH": str(self.root / "ld"),
            "SSL_CERT_FILE": str(self.root / "cert.pem"),
            "SSL_CERT_DIR": str(self.root / "certs"),
            "PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE": "0",
            "PYTHON_BUILD_EXTRA": "hostile",
            "VIRTUAL_ENV": str(self.root / "venv"),
            "CONDA_PREFIX": str(self.root / "conda"),
            "PKG_CONFIG_PATH": str(self.root / "pkgconfig"),
            "PKG_CONFIG_LIBDIR": str(self.root / "pkgconfig-libdir"),
            "CFLAGS": "-I" + str(homebrew / "include"),
            "LDFLAGS": "-L" + str(homebrew / "lib"),
            "HOMEBREW_PREFIX": str(homebrew),
            "HOMEBREW_CELLAR": str(homebrew / "Cellar"),
            "PATH": str(homebrew / "bin"),
            "HOME": str(self.root / "host-home"),
            "TMPDIR": str(self.root / "host-temp"),
        }
        probe = (
            "import importlib.util, json, os, site; "
            "print(json.dumps({"
            "'path': os.environ['PATH'], "
            "'home': os.environ['HOME'], "
            "'tmpdir': os.environ['TMPDIR'], "
            "'no_user_site': os.environ['PYTHONNOUSERSITE'], "
            "'user_site_enabled': site.ENABLE_USER_SITE, "
            "'injected_module': importlib.util.find_spec('product_process_injection') is not None, "
            "'scrubbed': {name: name not in os.environ for name in "
            "('PYTHONPATH', 'PYTHONHOME', 'PYTHONUSERBASE', 'DYLD_LIBRARY_PATH', "
            "'DYLD_FRAMEWORK_PATH', 'LD_LIBRARY_PATH', 'SSL_CERT_FILE', 'SSL_CERT_DIR', "
            "'PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE', 'PYTHON_BUILD_EXTRA', 'VIRTUAL_ENV', "
            "'CONDA_PREFIX', 'PKG_CONFIG_PATH', 'PKG_CONFIG_LIBDIR', 'CFLAGS', 'LDFLAGS', "
            "'HOMEBREW_PREFIX', 'HOMEBREW_CELLAR')}}))"
        )
        with patch.dict(os.environ, inherited):
            result = run_product_process(
                [sys.executable, "-c", probe],
                self.install,
                self.cwd,
                timeout_seconds=10,
            )

        observed = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            observed["path"],
            os.pathsep.join((str((self.install / "bin").resolve()), os.defpath)),
        )
        self.assertEqual(observed["home"], str(self.cwd.resolve()))
        self.assertEqual(observed["tmpdir"], str(self.cwd.resolve()))
        self.assertEqual(observed["no_user_site"], "1")
        self.assertFalse(observed["user_site_enabled"])
        self.assertFalse(observed["injected_module"])
        self.assertTrue(all(observed["scrubbed"].values()))
        self.assertNotIn(str(homebrew), observed["path"])

    def test_explicitly_allowed_overrides_reach_the_child(self) -> None:
        overrides = {
            "PYTHONHOME": sys.prefix,
            "SSL_CERT_FILE": "/chosen/cert.pem",
            "SSL_CERT_DIR": "/chosen/certs",
            "PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE": "1",
            "TERM": "xterm-256color",
            "TERMINFO_DIRS": "/chosen/terminfo",
            "DEVELOPER_DIR": "/chosen/developer",
            "SDKROOT": "/chosen/sdk",
            "TARGET_TRIPLE": "aarch64-apple-darwin",
            "EXPECTED_SQLITE_VERSION_INFO": "3,53,1",
            "EXPECTED_OPENSSL_VERSION_INFO": "3,5,0,7,0",
        }
        with patch.dict(os.environ, {"PATH": "/hostile/homebrew/bin"}):
            result = run_product_process(
                ["/usr/bin/env"],
                self.install,
                self.cwd,
                timeout_seconds=10,
                environment_overrides=overrides,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        observed = dict(line.split("=", 1) for line in result.stdout.splitlines())
        for name, value in overrides.items():
            self.assertEqual(observed[name], value)
        self.assertNotEqual(observed["PATH"], "/hostile/homebrew/bin")

    def test_product_environment_rejects_unsupported_override_names(self) -> None:
        with self.assertRaisesRegex(ValueError, "PATH"):
            product_environment(self.install, self.cwd, {"PATH": "/hostile"})

    def test_runner_rejects_empty_argv_and_invalid_timeouts(self) -> None:
        with self.assertRaises(ValueError):
            run_product_process([], self.install, self.cwd, timeout_seconds=1)

        for timeout in (0, -1, float("nan"), float("inf"), True, "1"):
            with self.subTest(timeout=timeout):
                with self.assertRaises(ValueError):
                    run_product_process(
                        ["/usr/bin/env"],
                        self.install,
                        self.cwd,
                        timeout_seconds=timeout,
                    )

        for executable, error in (("", ValueError), (object(), TypeError)):
            with self.subTest(executable=executable):
                with self.assertRaises(error):
                    run_product_process(
                        ["/dev/null"],
                        self.install,
                        self.cwd,
                        executable=executable,
                        timeout_seconds=1,
                    )

    def test_runner_propagates_launch_and_timeout_errors(self) -> None:
        with self.assertRaises(FileNotFoundError):
            run_product_process(
                [self.root / "missing-executable"],
                self.install,
                self.cwd,
                timeout_seconds=1,
            )

        with self.assertRaises(subprocess.TimeoutExpired):
            run_product_process(
                [sys.executable, "-c", "import signal; signal.pause()"],
                self.install,
                self.cwd,
                timeout_seconds=0.1,
            )

    def test_runner_preserves_unusual_argv_zero_with_controlled_executable(self) -> None:
        result = run_product_process(
            ["/dev/null", "-c", "print(42)"],
            self.install,
            self.cwd,
            executable=sys.executable,
            timeout_seconds=10,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "42")


if __name__ == "__main__":
    unittest.main()
