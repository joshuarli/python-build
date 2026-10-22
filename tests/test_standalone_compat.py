from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from buildsys.product import PRODUCT
from buildsys.standalone_compat import (
    CompatibilityError,
    _compatibility_status,
    _isolated_environment,
    run_standalone_compatibility,
)
from buildsys.targets import TARGETS


class CompatibilityStatusTests(unittest.TestCase):
    def test_false_probe_result_is_a_failure(self) -> None:
        self.assertEqual(_compatibility_status({"ok": False}), "failed")

    def test_explicit_failure_status_is_preserved(self) -> None:
        self.assertEqual(_compatibility_status({"status": "failed"}), "failed")

    def test_successful_probe_result_passes(self) -> None:
        self.assertEqual(_compatibility_status({"ok": True}), "passed")

    def test_isolated_environment_contains_only_validation_overrides(self) -> None:
        with patch.dict(os.environ, {
            "PYTHONPATH": "/hostile/pythonpath",
            "SSL_CERT_FILE": "/hostile/cert.pem",
            "DYLD_LIBRARY_PATH": "/hostile/dylibs",
            "HOMEBREW_PREFIX": "/opt/homebrew",
        }):
            environment = _isolated_environment(TARGETS["aarch64-apple-darwin"])

        self.assertEqual(environment["TARGET_TRIPLE"], "aarch64-apple-darwin")
        self.assertEqual(environment["TERM"], "xterm")
        self.assertNotIn("PYTHONPATH", environment)
        self.assertNotIn("SSL_CERT_FILE", environment)
        self.assertNotIn("DYLD_LIBRARY_PATH", environment)
        self.assertNotIn("HOMEBREW_PREFIX", environment)

    def test_stale_interpreter_path_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            install = Path(temporary)
            stale_minor = f"{PRODUCT.version[0]}.{PRODUCT.version[1] - 1}"
            stale = install / "bin" / f"python{stale_minor}"
            with self.assertRaisesRegex(CompatibilityError, "expected product interpreter"):
                run_standalone_compatibility(
                    stale, install, TARGETS["aarch64-apple-darwin"]
                )

    def test_missing_mandatory_runtime_check_makes_aggregate_fail(self) -> None:
        runtime_names = (
            "compression", "ctypes_callbacks", "hashlib_algorithms",
            "testcapi_modules", "sqlite_features", "ssl_capabilities",
            "zstd_multithreading", "gil_and_hash_policy", "product_identity",
            "target_abi", "linux_uapi_sysconfig", "linux_mdwe_thread_creation",
        )
        checks = {name: {"status": "passed"} for name in runtime_names}
        checks.pop("product_identity")
        output = json.dumps({"checks": checks, "not_applicable": {}, "ok": True})
        process = subprocess.CompletedProcess([], 0, output, "")
        success = {"status": "passed", "ok": True}

        with tempfile.TemporaryDirectory() as temporary:
            install = Path(temporary)
            python = PRODUCT.interpreter(install)
            with (
                patch("buildsys.standalone_compat.run_product_process", return_value=process) as runner,
                patch("buildsys.standalone_compat._getpath_check", return_value=success),
                patch("buildsys.standalone_compat._relocated_sysconfig_check", return_value=success),
                patch("buildsys.standalone_compat._fallback_ca_check", return_value=success),
                patch("buildsys.standalone_compat._curses_tty_check", return_value=success),
            ):
                report = run_standalone_compatibility(
                    python, install, TARGETS["aarch64-apple-darwin"]
                )

        self.assertFalse(report["ok"])
        self.assertIn("product_identity", report["aggregate"]["failed"])
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(
            runner.call_args.kwargs["environment_overrides"]["TARGET_TRIPLE"],
            "aarch64-apple-darwin",
        )


if __name__ == "__main__":
    unittest.main()
