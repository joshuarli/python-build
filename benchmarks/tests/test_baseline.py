"""Tests for compact, version-controlled benchmark baseline snapshots."""

from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from benchmarks import bench as benchmark_cli
from benchmarks.harness.baseline import (
    _pyperformance_measurements,
    baseline_snapshot_path,
    build_baseline_snapshot,
    save_baseline_snapshot,
    update_baseline_snapshot,
)


class BaselineSnapshotTests(unittest.TestCase):
    def make_run(self, root: Path) -> Path:
        run = root / "run"
        workload = run / "realworld" / "sample_workload"
        workload.mkdir(parents=True)
        provenance = {
            "timestamp_utc": "2026-09-24T00:00:00+00:00",
            "git_commit": "abc123",
            "suite": "realworld",
            "profile": "rigorous",
            "offline_boundary": "docker --network none",
            "benchmark_lock_sha256": "lock-hash",
            "benchmark_tool_versions": {"memray": "1.20.0"},
            "benchmark_image_id": "sha256:image",
            "container_runtime_version": "29.5.2/29.5.2",
            "memory_sampling_interval_seconds": 0.01,
            "baseline": {
                "label": "self-comparison control",
                "kind": "self",
                "version": [3, 14, 7],
                "executable_sha256": "python-hash",
            },
            "host": {
                "system": "Linux",
                "machine": "x86_64",
                "kernel_release": "6.18.33",
                "cpu_model": "Example CPU",
                "physical_core_count": 16,
                "logical_cpu_count": 32,
                "memory_total_bytes": 64_000_000_000,
                "cpu_governors": ["powersave"],
                "cpu_affinity": {"selected_cpus": [0]},
            },
        }
        summary = {
            "suite": "realworld",
            "profile": "rigorous",
            "workloads": [
                {
                    "identity": {
                        "name": "sample_workload",
                        "category": "startup",
                        "operation": "process",
                        "operation_count": 1,
                        "digest": "ok",
                    }
                }
            ],
        }
        raw = {
            "identity": {
                "name": "sample_workload",
                "category": "startup",
                "operation": "process",
                "operation_count": 1,
                "digest": "ok",
            },
            "baseline": {
                "timing": {"samples": [1.0, 1.2, 1.1]},
                "memory": {
                    "rounds": [
                        {"peak_pss": 100, "peak_rss": 120, "peak_private": 80, "steady_pss": 90},
                        {"peak_pss": 110, "peak_rss": 130, "peak_private": 85, "steady_pss": 95},
                    ]
                },
                "allocations": {
                    "rounds": [
                        {
                            "status": "complete",
                            "operations": 1,
                            "total_num_allocations": 10,
                            "total_bytes_allocated": 500,
                            "bytes_allocated_per_operation": 500.0,
                            "profiler": "memray",
                            "profiler_version": "1.20.0",
                            "capture_path": "/tmp/raw-capture.memray.bin",
                        }
                    ]
                },
            },
            "candidate": {},
        }
        (run / "provenance.json").write_text(json.dumps(provenance))
        (run / "summary.json").write_text(json.dumps(summary))
        (workload / "raw.json").write_text(json.dumps(raw))
        return run

    def test_snapshot_keeps_baseline_metrics_and_runner_specs_without_capture_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            run = self.make_run(Path(temp))
            snapshot = build_baseline_snapshot(
                run,
                recorded_at=datetime(2026, 9, 24, tzinfo=timezone.utc),
            )

        self.assertEqual(snapshot["schema_version"], 1)
        self.assertEqual(snapshot["comparison_role"], "self_control_calibration")
        self.assertEqual(snapshot["reference_interpreter"]["version"], [3, 14, 7])
        self.assertEqual(snapshot["runner"]["cpu_model"], "Example CPU")
        self.assertEqual(snapshot["runner"]["physical_core_count"], 16)
        self.assertEqual(snapshot["runner"]["memory_total_bytes"], 64_000_000_000)
        workload = snapshot["workloads"][0]
        self.assertEqual(workload["timing_seconds"]["median"], 1.1)
        self.assertEqual(workload["memory_bytes"]["peak_pss"]["median"], 105)
        self.assertEqual(workload["allocations"]["round_count"], 1)
        self.assertNotIn("capture_path", workload["allocations"]["rounds"][0])

    def test_pyperformance_snapshot_retains_group_coverage(self):
        comparison = {
            "suite_version": "1.14.0",
            "pyperf_version": "2.10.0",
            "groups": {"stdlib": {"selected_count": 1, "recorded_count": 1}},
            "benchmarks": [
                {
                    "name": "json_loads",
                    "groups": ["stdlib"],
                    "baseline_timing": {"samples": [0.1, 0.2, 0.3]},
                    "baseline_memory": {
                        "samples": [1000, 1100],
                        "mem_max_rss": 2000,
                        "command_max_rss": None,
                    },
                }
            ],
        }

        snapshot = _pyperformance_measurements(comparison)
        self.assertEqual(snapshot["groups"]["stdlib"]["recorded_count"], 1)
        self.assertEqual(snapshot["benchmarks"][0]["timing_seconds"]["median"], 0.2)
        self.assertEqual(snapshot["benchmarks"][0]["memory_bytes"]["median"], 1050)

    def test_automatic_update_reuses_stable_target_and_refreshes_measurements(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = self.make_run(root)
            baseline_directory = root / "baselines"
            expected_path = baseline_snapshot_path(
                build_baseline_snapshot(run), baseline_directory
            )
            first_path = update_baseline_snapshot(run, baseline_directory)
            first = json.loads(first_path.read_text())

            raw_path = run / "realworld" / "sample_workload" / "raw.json"
            raw = json.loads(raw_path.read_text())
            raw["baseline"]["timing"]["samples"] = [2.0, 2.2, 2.1]
            raw_path.write_text(json.dumps(raw))
            provenance_path = run / "provenance.json"
            provenance = json.loads(provenance_path.read_text())
            provenance["timestamp_utc"] = "2026-09-25T00:00:00+00:00"
            provenance_path.write_text(json.dumps(provenance))

            second_path = update_baseline_snapshot(run, baseline_directory)
            second = json.loads(second_path.read_text())

        self.assertEqual(second_path, first_path)
        self.assertEqual(first_path, expected_path)
        self.assertEqual(first["workloads"][0]["timing_seconds"]["median"], 1.1)
        self.assertEqual(second["workloads"][0]["timing_seconds"]["median"], 2.1)

    def test_successful_run_automatically_records_a_baseline(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = self.make_run(root)
            benchmark_directory = root / "benchmarks"
            with patch.object(benchmark_cli, "BENCH", benchmark_directory):
                with patch.object(benchmark_cli, "_run_container", return_value=run):
                    with redirect_stdout(io.StringIO()):
                        status = benchmark_cli.main(
                            ["run", "--baseline", "baseline", "--candidate", "candidate"]
                        )

            snapshots = list((benchmark_directory / "baselines").glob("*.json"))
            saved = json.loads(snapshots[0].read_text())

        self.assertEqual(status, 0)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(saved["comparison_role"], "self_control_calibration")
        self.assertEqual(saved["workloads"][0]["name"], "sample_workload")

    def test_writer_refuses_to_overwrite_a_baseline(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = self.make_run(root)
            destination = root / "baselines" / "sample.json"
            saved = save_baseline_snapshot(run, destination)
            self.assertTrue(saved.is_file())
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                save_baseline_snapshot(run, destination)


if __name__ == "__main__":
    unittest.main()
