"""Tests for external Linux memory-accounting parsers and totals."""

from __future__ import annotations

import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

from benchmarks.harness.memory import (
    CgroupV2MemoryScope,
    MemorySample,
    ProcessMemoryMetrics,
    SmapsRollupError,
    parse_cgroup_memory_events,
    parse_smaps_rollup,
    sum_rollups,
)


class SmapsRollupTests(unittest.TestCase):
    def test_parses_resident_private_shared_and_swap_values_as_bytes(self):
        parsed = parse_smaps_rollup(
            """00400000-00452000 r-xp 00000000 08:02 123 /usr/bin/python3
Rss:                 1024 kB
Pss:                  768 kB
Shared_Clean:         128 kB
Shared_Dirty:          64 kB
Private_Clean:        256 kB
Private_Dirty:        576 kB
Shared_Hugetlb:         2 kB
Private_Hugetlb:        4 kB
Swap:                  12 kB
"""
        )

        self.assertEqual(parsed.rss_bytes, 1024 * 1024)
        self.assertEqual(parsed.pss_bytes, 768 * 1024)
        self.assertEqual(parsed.private_bytes, 836 * 1024)
        self.assertEqual(parsed.shared_clean_bytes, 128 * 1024)
        self.assertEqual(parsed.shared_dirty_bytes, 64 * 1024)
        self.assertEqual(parsed.swap_bytes, 12 * 1024)

    def test_older_kernel_missing_hugetlb_counters_uses_zero(self):
        parsed = parse_smaps_rollup(
            """Rss: 10 kB
Pss: 8 kB
Private_Clean: 2 kB
Private_Dirty: 3 kB
Swap: 1 kB
"""
        )

        self.assertEqual(parsed.private_bytes, 5 * 1024)
        self.assertEqual(parsed.shared_clean_bytes, 0)

    def test_rejects_incomplete_or_non_kilobyte_core_fields(self):
        with self.assertRaisesRegex(SmapsRollupError, "Pss"):
            parse_smaps_rollup("Rss: 1 kB\n")
        with self.assertRaisesRegex(SmapsRollupError, "unsupported unit"):
            parse_smaps_rollup(
                "Rss: 1 MB\nPss: 1 kB\nPrivate_Clean: 0 kB\n"
                "Private_Dirty: 0 kB\nSwap: 0 kB\n"
            )


class ProcessMemoryMetricsTests(unittest.TestCase):
    def test_sums_tree_rollups_and_builds_peak_boundary_metrics(self):
        parent = parse_smaps_rollup(
            "Rss: 100 kB\nPss: 60 kB\nPrivate_Clean: 20 kB\n"
            "Private_Dirty: 30 kB\nSwap: 2 kB\n"
        )
        child = parse_smaps_rollup(
            "Rss: 200 kB\nPss: 40 kB\nPrivate_Clean: 10 kB\n"
            "Private_Dirty: 20 kB\nSwap: 4 kB\n"
        )
        sample = sum_rollups({101: parent, 102: child}, 0.1)
        later = MemorySample(
            elapsed_seconds=0.2,
            rss_bytes=sample.rss_bytes + 1024,
            pss_bytes=sample.pss_bytes + 2048,
            private_bytes=sample.private_bytes + 3072,
            swap_bytes=sample.swap_bytes,
            process_count=1,
            pids=(101,),
        )
        metrics = ProcessMemoryMetrics.from_samples([sample, later])

        self.assertEqual(sample.process_count, 2)
        self.assertEqual(sample.rss_bytes, 300 * 1024)
        self.assertEqual(sample.pss_bytes, 100 * 1024)
        self.assertEqual(sample.private_bytes, 80 * 1024)
        self.assertEqual(sample.swap_bytes, 6 * 1024)
        self.assertEqual(metrics.peak_pss_bytes, later.pss_bytes)
        self.assertEqual(metrics.peak_process_count, 2)
        self.assertIsNone(metrics.steady_pss_bytes)
        metrics.phase_samples["steady"] = later
        self.assertEqual(metrics.steady_pss_bytes, later.pss_bytes)
        self.assertEqual(metrics.as_dict()["peak_pss_bytes"], later.pss_bytes)


class CgroupV2MemoryTests(unittest.TestCase):
    def _fake_child(self, parent: Path) -> Path:
        child = parent / "python-build-bench-test"
        child.mkdir()
        (child / "cgroup.procs").write_text("", encoding="ascii")
        (child / "memory.current").write_text("0\n", encoding="ascii")
        (child / "memory.peak").write_text("0\n", encoding="ascii")
        (child / "memory.events").write_text("low 0\nhigh 0\nmax 0\noom 0\n", encoding="ascii")
        return child

    def _remove_fake_child(self, child: Path) -> None:
        for path in child.iterdir():
            path.unlink()
        child.rmdir()

    def test_parses_cgroup_memory_events_and_rejects_malformed_counters(self):
        self.assertEqual(
            parse_cgroup_memory_events("low 1\nhigh 0\noom_kill 2\n"),
            {"low": 1, "high": 0, "oom_kill": 2},
        )
        with self.assertRaises(ValueError):
            parse_cgroup_memory_events("oom not-a-count\n")

    def test_delegated_scope_attaches_reads_and_removes_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            (parent / "cgroup.controllers").write_text("cpu memory pids\n", encoding="ascii")
            (parent / "cgroup.subtree_control").write_text("memory\n", encoding="ascii")
            child = self._fake_child(parent)
            with (
                patch("benchmarks.harness.memory._create_child_cgroup", return_value=child),
                patch("benchmarks.harness.memory._remove_cgroup_directory", side_effect=self._remove_fake_child),
            ):
                scope = CgroupV2MemoryScope.create_under(parent)
                self.assertIsNotNone(scope)
                assert scope is not None
                scope.attach_pid(1234)
                self.assertEqual((child / "cgroup.procs").read_text(encoding="ascii"), "1234\n")
                (child / "memory.current").write_text("4096\n", encoding="ascii")
                (child / "memory.peak").write_text("8192\n", encoding="ascii")
                (child / "memory.events").write_text("low 0\nmax 1\noom 0\n", encoding="ascii")
                snapshot = scope.read_snapshot()
                self.assertEqual(snapshot.current_bytes, 4096)
                self.assertEqual(snapshot.peak_bytes, 8192)
                self.assertEqual(snapshot.events, {"low": 0, "max": 1, "oom": 0})
                scope.close()
                self.assertFalse(child.exists())
                self.assertIsNone(scope.cleanup_error)

    def test_scope_is_not_created_without_delegated_memory_controller(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            (parent / "cgroup.controllers").write_text("cpu pids\n", encoding="ascii")
            (parent / "cgroup.subtree_control").write_text("\n", encoding="ascii")
            with patch("benchmarks.harness.memory._create_child_cgroup") as create:
                self.assertIsNone(CgroupV2MemoryScope.create_under(parent))
                create.assert_not_called()

    def test_detects_current_v2_subtree_from_proc_fixtures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = root / "proc" / "self"
            proc.mkdir(parents=True)
            mount = root / "cgroup"
            parent = mount / "benchmark-parent"
            parent.mkdir(parents=True)
            (proc / "cgroup").write_text("0::/benchmark-parent\n", encoding="ascii")
            (proc / "mountinfo").write_text(
                f"39 22 0:31 / {mount} rw - cgroup2 cgroup rw\n", encoding="ascii"
            )
            (parent / "cgroup.controllers").write_text("memory\n", encoding="ascii")
            (parent / "cgroup.subtree_control").write_text("memory\n", encoding="ascii")
            child = self._fake_child(parent)
            with (
                patch("benchmarks.harness.memory._create_child_cgroup", return_value=child),
                patch("benchmarks.harness.memory._remove_cgroup_directory", side_effect=self._remove_fake_child),
            ):
                scope = CgroupV2MemoryScope.detect_and_create(proc_root=root / "proc")
                self.assertIsNotNone(scope)
                assert scope is not None
                self.assertEqual(scope.path.parent, parent)
                scope.close()


if __name__ == "__main__":
    unittest.main()
