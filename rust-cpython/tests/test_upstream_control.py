from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

LANE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LANE))
import upstream_control as control  # noqa: E402


class UpstreamControlContractTests(unittest.TestCase):
    def test_artifact_identity_records_exact_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "profile.profclangd"
            path.write_bytes(b"profile bytes\n")
            record = control._artifact_identity(path)
            self.assertEqual(record, {
                "path": str(path),
                "size": len(b"profile bytes\n"),
                "sha256": hashlib.sha256(b"profile bytes\n").hexdigest(),
            })
            with self.assertRaisesRegex(control.ControlError, "missing"):
                control._artifact_identity(path.with_name("absent.profclangd"))

    def test_source_pin_is_vanilla_and_separate_from_fork(self) -> None:
        item = control.source_input()
        self.assertEqual(item.sha256, "7b8b68534a75aee0003457d42bf9e77a29bb948544cd993a3e059df811eecc7f")
        self.assertEqual(item.size, 44189176)
        self.assertEqual(item.role, "test")
        self.assertIn(control.COMMIT, item.url)
        self.assertNotEqual(control.LOCK, control.FORK.SOURCE_LOCK)
        self.assertNotEqual(control.STAGE, control.FORK.STAGE)
        self.assertNotEqual(control.SOURCE, control.FORK.SOURCE)

    def test_rejects_an_unreviewed_source_revision(self) -> None:
        altered = control.LOCK.read_text().replace(control.COMMIT, "0" * 40)
        with tempfile.TemporaryDirectory() as temporary:
            lock = Path(temporary) / "upstream.sources.lock.json"
            lock.write_text(altered)
            with patch.object(control, "LOCK", lock):
                with self.assertRaisesRegex(control.ControlError, "merge base"):
                    control.source_input()

    def test_configuration_matches_fork_c_recipe_without_cargo(self) -> None:
        toolchain, target = control.FORK._toolchain()
        with patch.object(control.FORK, "_brew_pkg_config_path", return_value=""):
            env = control._environment(toolchain, target, 3)
        self.assertEqual(env["PROFILE_TASK"], "-m test --pgo -j 3")
        self.assertEqual(env["LLVM_PROFDATA"], str(toolchain.llvm_profdata))
        self.assertIn("-O3", env["CFLAGS"])
        self.assertIn(target.cpu_baseline_cflag, env["CFLAGS"])
        self.assertEqual(env["IPHONEOS_DEPLOYMENT_TARGET"], "")
        self.assertNotIn("cargo", env["PATH"].lower())
        self.assertNotIn("CARGO_TARGET_DIR", env)


if __name__ == "__main__":
    unittest.main()
