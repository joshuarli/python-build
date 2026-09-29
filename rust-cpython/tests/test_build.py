"""Private Rust launchers must work without ambient compiler proxies."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest import mock

LANE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LANE))

import perf


class RustLauncherTests(unittest.TestCase):
    def test_cargo_can_find_the_pinned_rustc_on_the_private_path(self):
        with tempfile.TemporaryDirectory(prefix="rust launcher ") as temporary:
            root = Path(temporary)
            rustup = root / "rustup"
            rustup.write_text(
                '#!/bin/sh\n'
                'test "$1" = run || exit 10\n'
                f'test "$2" = {perf.lb.RUST_CHANNEL} || exit 11\n'
                'case "$3" in\n'
                'cargo) printf "cargo\\n"; rustc -V ;;\n'
                'rustc) printf "pinned-rustc\\n" ;;\n'
                '*) exit 12 ;;\n'
                'esac\n'
            )
            rustup.chmod(0o755)
            cargo_home = root / "cargo-home"
            with mock.patch.object(perf.lb, "CARGO_HOME", cargo_home):
                cargo = perf.lb._rust_tool_wrappers(str(rustup))
            env = dict(os.environ, PATH=str(cargo_home / "bin"))
            result = subprocess.run([str(cargo), "-V"], env=env,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "cargo\npinned-rustc\n")


class MacOSDependencyProbeTests(unittest.TestCase):
    def test_mpdecimal_metadata_is_visible_to_configure(self):
        with tempfile.TemporaryDirectory() as temporary:
            prefix = Path(temporary)
            pkgconfig = prefix / "lib" / "pkgconfig"
            pkgconfig.mkdir(parents=True)
            def command(argv):
                if argv == ["brew", "--prefix", "mpdecimal"]:
                    return {"returncode": 0, "output": str(prefix)}
                return {"returncode": 1, "output": ""}
            with mock.patch.object(perf.lb.shutil, "which", return_value="brew"), \
                    mock.patch.object(perf.lb, "_command", side_effect=command):
                found = perf.lb._brew_pkg_config_path().split(":")
            self.assertIn(str(pkgconfig), found)


class MacOSDeploymentProbeTests(unittest.TestCase):
    def test_new_sdk_posix_functions_are_disabled_below_their_introduction(self):
        toolchain = SimpleNamespace(deployment_target="26.0", sdkroot=Path("/SDK"))
        target = SimpleNamespace(cpu_baseline_cflag="-mcpu=apple-m1")
        with mock.patch.object(perf.lb, "IS_LINUX", False), \
                mock.patch.object(perf.lb, "_brew_pkg_config_path", return_value=""):
            for flags in (perf.lb._platform_flags(toolchain, target),
                          perf._perf_flags(toolchain, target)):
                self.assertEqual(flags.get("ac_cv_func_dup3"), "no")
                self.assertEqual(flags.get("ac_cv_func_pipe2"), "no")

    def test_supported_posix_functions_remain_probeable_at_their_introduction(self):
        toolchain = SimpleNamespace(deployment_target="27.0", sdkroot=Path("/SDK"))
        target = SimpleNamespace(cpu_baseline_cflag="-mcpu=apple-m1")
        with mock.patch.object(perf.lb, "IS_LINUX", False), \
                mock.patch.object(perf.lb, "_brew_pkg_config_path", return_value=""):
            for flags in (perf.lb._platform_flags(toolchain, target),
                          perf._perf_flags(toolchain, target)):
                self.assertNotIn("ac_cv_func_dup3", flags)
                self.assertNotIn("ac_cv_func_pipe2", flags)


if __name__ == "__main__":
    unittest.main()
