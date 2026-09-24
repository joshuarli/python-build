"""Behavior tests for optional perf stat diagnostics."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.harness import perf


class PerfStatTests(unittest.TestCase):
    def test_csv_parser_maps_counts_and_unsupported_events(self) -> None:
        parsed = perf.parse_perf_stat(
            "12,,cycles,100.0,\n"
            "24,,instructions,100.0,\n"
            "<not counted>,,cache-misses,0.0,\n"
            "# comment\n",
            ("cycles", "instructions", "cache-misses"),
        )
        self.assertEqual(parsed, {"cycles": 12.0, "instructions": 24.0, "cache-misses": None})

    def test_disabled_mode_skips_without_running_perf(self) -> None:
        with patch.object(perf.subprocess, "run") as run:
            report = perf.run_perf_stat(["python", "-c", "pass"])
        run.assert_not_called()
        self.assertEqual(report["status"], "skipped")

    def test_permission_denial_is_unavailable_without_setting_mutation(self) -> None:
        completed = subprocess.CompletedProcess(
            ["perf", "stat"], 255, stdout="", stderr="Error: No permission to enable cycles event.\n"
        )
        with tempfile.TemporaryDirectory() as temporary:
            output_path = Path(temporary) / "perf.json"
            with patch.object(perf.shutil, "which", return_value="/usr/bin/perf"), patch.object(
                perf.subprocess, "run", return_value=completed
            ) as run:
                report = perf.run_perf_stat(
                    ["python", "-c", "pass"],
                    enabled=True,
                    operations=2,
                    output_json=output_path,
                    env={"LC_ALL": "C.UTF-8"},
                )
            self.assertEqual(report["status"], "unavailable")
            self.assertIn("No permission", report["reason"])
            self.assertEqual(json.loads(output_path.read_text())["status"], "unavailable")
            self.assertEqual(run.call_args.args[0][-4:], ["--", "python", "-c", "pass"])
            self.assertEqual(run.call_args.kwargs["env"]["LC_ALL"], "C")
            self.assertIn("LC_ALL=C.UTF-8", run.call_args.args[0])

    def test_completed_run_normalizes_counters_per_operation(self) -> None:
        completed = subprocess.CompletedProcess(
            ["perf", "stat"],
            0,
            stdout="",
            stderr=(
                "100,,cycles,100.0,\n"
                "300,,instructions,100.0,\n"
                "20,,cache-misses,100.0,\n"
                "4,,page-faults,100.0,\n"
            ),
        )
        with patch.object(perf.shutil, "which", return_value="/usr/bin/perf"), patch.object(
            perf.subprocess, "run", return_value=completed
        ):
            report = perf.run_perf_stat(
                ["python", "-m", "workload"], enabled=True, operations=10
            )
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["counters"]["cycles"], 100)
        self.assertEqual(report["normalized"]["instructions_per_operation"], 30)
        self.assertEqual(report["normalized"]["cycles_per_operation"], 10)
        self.assertEqual(report["normalized"]["cache_misses_per_operation"], 2)
        self.assertEqual(report["normalized"]["faults_per_operation"], 0.4)
        self.assertEqual(report["normalized"]["ipc"], 3)


if __name__ == "__main__":
    unittest.main()
