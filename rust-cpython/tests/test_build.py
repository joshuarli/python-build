"""Private Rust launchers must work without ambient compiler proxies."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
