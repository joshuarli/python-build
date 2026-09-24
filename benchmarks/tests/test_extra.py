from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from benchmarks.workloads import extra


class ExtraWorkloadTests(unittest.TestCase):
    def test_startup_cli_emits_json_as_its_last_stdout_line(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = extra.main(["python_startup_no_site", "--iterations", "1"])
        self.assertEqual(status, 0)
        result = __import__("json").loads(output.getvalue().splitlines()[-1])
        self.assertEqual(result["operation_count"], 1)
        self.assertEqual(len(result["digest"]), 64)
        self.assertGreaterEqual(result["elapsed_seconds"], 0)

    def test_fresh_import_helper_confirms_each_module(self) -> None:
        result = extra._import_fresh_process(("json", "pathlib"), 1, "test_import")
        self.assertEqual(result["operation_count"], 1)
        self.assertEqual(len(result["digest"]), 64)

    def test_serialization_roundtrip_preserves_deterministic_shared_graph(self) -> None:
        first = extra.serialization_roundtrip(2)
        second = extra.serialization_roundtrip(1)
        self.assertEqual(first["operation_count"], 2)
        self.assertEqual(first["digest"], second["digest"])
        self.assertGreaterEqual(first["elapsed_seconds"], 0)

    def test_multiprocess_pool_validates_worker_results(self) -> None:
        first = extra.multiprocess_pool(4)
        second = extra.multiprocess_pool(4)
        self.assertEqual(first["operation_count"], 4)
        self.assertEqual(first["digest"], second["digest"])

    def test_pip_install_is_offline_fresh_and_inventory_checked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheelhouse = Path(temporary) / "wheelhouse"
            wheelhouse.mkdir()
            commands: list[list[str]] = []

            def fake_pip(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                target = Path(command[command.index("--target") + 1])
                self.assertFalse(target.exists())
                metadata = target / "Example_Pkg-1.2.3.dist-info"
                metadata.mkdir(parents=True)
                (metadata / "METADATA").write_text(
                    "Metadata-Version: 2.1\nName: Example-Pkg\nVersion: 1.2.3\n\n",
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch.dict(
                os.environ,
                {
                    "BENCH_WHEELHOUSE": str(wheelhouse),
                    "BENCH_PIP_PACKAGES": "Example-Pkg==1.2.3",
                },
            ), patch.object(extra.subprocess, "run", side_effect=fake_pip):
                result = extra.pip_install_wheelhouse(2)

        self.assertEqual(result["operation_count"], 2)
        self.assertEqual(len(commands), 2)
        for command in commands:
            self.assertIn("--no-index", command)
            self.assertIn("--ignore-installed", command)
            self.assertIn("--only-binary=:all:", command)
            self.assertIn(str(wheelhouse.resolve()), command)
        first_target = commands[0][commands[0].index("--target") + 1]
        second_target = commands[1][commands[1].index("--target") + 1]
        self.assertNotEqual(first_target, second_target)

    def test_pip_install_requires_exact_pins(self) -> None:
        with patch.dict(os.environ, {"BENCH_PIP_PACKAGES": "Django>=6"}):
            with self.assertRaisesRegex(extra.WorkloadError, "pinned as name==version"):
                extra._pinned_packages()

    def test_cli_rejects_zero_iterations(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                extra.main(["python_startup", "--iterations", "0"])
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
