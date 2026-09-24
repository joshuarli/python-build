"""Tests for paired workload execution policy."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.harness import runner
from benchmarks.workloads.registry import Workload


class TimingOnlyRunnerTests(unittest.TestCase):
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
