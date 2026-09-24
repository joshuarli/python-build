"""Tests for paired workload execution policy."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import math
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.harness import runner
from benchmarks.workloads.registry import Workload


class TimingOnlyRunnerTests(unittest.TestCase):
    def test_cold_import_adds_reported_direct_child_cpu_once(self) -> None:
        measured = SimpleNamespace(
            cpu_user_seconds=0.2, cpu_system_seconds=0.1,
            cpu_coverage="wait4 root only; descendants excluded",
        )
        payload = {"operation_count": 2, "reaped_child_cpu": {
            "user_seconds": 0.4, "system_seconds": 0.2, "process_count": 2,
        }}
        cpu = runner._cpu_dict(measured, payload, "zipimport_cold")
        self.assertAlmostEqual(cpu["user_seconds"], 0.6)
        self.assertAlmostEqual(cpu["system_seconds"], 0.3)
        self.assertAlmostEqual(cpu["total_seconds_per_operation"], 0.45)
        self.assertEqual(cpu["root_user_seconds"], 0.2)
        self.assertEqual(cpu["root_system_seconds"], 0.1)
        self.assertEqual(cpu["reaped_child_cpu"], payload["reaped_child_cpu"])
        self.assertIn("direct reaped children", cpu["coverage"])

    def test_cold_import_rejects_missing_or_invalid_child_cpu(self) -> None:
        measured = SimpleNamespace(cpu_user_seconds=0.2, cpu_system_seconds=0.1,
                                   cpu_coverage="wait4 root only; descendants excluded")
        for child in (None, {"user_seconds": math.nan, "system_seconds": 0.1,
                             "process_count": 2},
                      {"user_seconds": 0.1, "system_seconds": math.inf,
                       "process_count": 2},
                      {"user_seconds": -0.1, "system_seconds": 0.1,
                       "process_count": 2},
                      {"user_seconds": 0.1, "process_count": 2},
                      {"user_seconds": 0.1, "system_seconds": 0.1,
                       "process_count": 1}):
            with self.subTest(child=child), self.assertRaises(RuntimeError):
                runner._cpu_dict(measured, {"operation_count": 2,
                                            "reaped_child_cpu": child}, "zipimport_cold")

    def test_noisy_workloads_do_not_restore_memory_rounds(self) -> None:
        workload = Workload(
            "python_startup", "startup", "extra", "process", 1, 1,
            noise_class="noisy",
        )
        completed = SimpleNamespace(
            cleanup_complete=True,
            remaining_pids=(),
            returncode=0,
            timed_out=False,
            stdout=b"",
            stderr=b"",
            duration_seconds=0.01,
            memory=None,
        )
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "workload"
            with patch.object(runner, "run_command", return_value=completed) as run:
                result = runner.run_workload(
                    workload,
                    Path("/baseline/python"),
                    Path("/candidate/python"),
                    profile="quick",
                    site_packages=None,
                    output_dir=output_dir,
                    measure_memory=False,
                )

        self.assertEqual(run.call_count, 6)  # two warmups plus two paired timing rounds
        self.assertTrue(
            all(call.kwargs["sample_interval_seconds"] is None for call in run.call_args_list)
        )
        for side in ("baseline", "candidate"):
            self.assertEqual(result[side]["memory"]["rounds"], [])
            self.assertEqual(result[side]["memory"]["status"], "not_measured")


if __name__ == "__main__":
    unittest.main()
