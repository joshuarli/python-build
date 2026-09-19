"""Tests for the head-to-head musl benchmark harness (benchmarks/).

Unit-level only: no Docker, no network. The Docker image build and the
rigorous runs themselves are exercised by benchmarks/run_benchmarks.sh.
"""

import ast
import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks"


def load_compare_module():
    spec = importlib.util.spec_from_file_location(
        "bench_compare", BENCH / "compare.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_results(path: Path, means: dict[str, float]) -> None:
    suite = {
        "benchmarks": [
            {
                "metadata": {"name": name},
                "runs": [{"values": [mean, mean]}],
            }
            for name, mean in means.items()
        ]
    }
    path.write_text(json.dumps(suite))


class CompareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compare = load_compare_module()

    def compare_means(self, pbs: dict[str, float], ours: dict[str, float]) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            pbs_path = Path(tmp) / "pbs.json"
            ours_path = Path(tmp) / "ours.json"
            write_results(pbs_path, pbs)
            write_results(ours_path, ours)
            return self.compare.compare(pbs_path, ours_path)

    def test_identical_runs_score_exactly_one(self):
        report = self.compare_means({"a": 1.0, "b": 2.0}, {"a": 1.0, "b": 2.0})
        self.assertAlmostEqual(report["geomean_ours_over_pbs"], 1.0)
        self.assertTrue(report["pass"])

    def test_half_percent_slower_passes(self):
        report = self.compare_means({"a": 1.0, "b": 2.0}, {"a": 1.005, "b": 2.01})
        self.assertAlmostEqual(report["geomean_ours_over_pbs"], 1.005)
        self.assertTrue(report["pass"])

    def test_two_percent_slower_fails(self):
        report = self.compare_means({"a": 1.0, "b": 2.0}, {"a": 1.02, "b": 2.04})
        self.assertFalse(report["pass"])
        self.assertAlmostEqual(report["delta_pct"], 2.0)

    def test_faster_build_passes(self):
        report = self.compare_means({"a": 1.0}, {"a": 0.992})
        self.assertTrue(report["pass"])
        self.assertLess(report["geomean_ours_over_pbs"], 1.0)

    def test_mp_pool_excluded_from_verdict_but_reported(self):
        report = self.compare_means(
            {"a": 1.0, "bench_mp_pool": 1.0},
            {"a": 1.0, "bench_mp_pool": 1.5},
        )
        self.assertTrue(report["pass"])
        self.assertIn("bench_mp_pool", report["excluded_from_verdict"])
        self.assertAlmostEqual(
            report["excluded_from_verdict"]["bench_mp_pool"], 1.5
        )

    def test_non_common_benchmarks_are_listed_and_ignored(self):
        report = self.compare_means(
            {"a": 1.0, "pbs_extra": 3.0}, {"a": 1.0, "ours_extra": 4.0}
        )
        self.assertTrue(report["pass"])
        self.assertEqual(report["pbs_only"], ["pbs_extra"])
        self.assertEqual(report["ours_only"], ["ours_extra"])
        self.assertNotIn("pbs_extra", report["ratios"])

    def test_no_common_benchmarks_raises(self):
        with self.assertRaises(ValueError):
            self.compare_means({"a": 1.0}, {"b": 1.0})

    def test_empty_suite_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty.json"
            full = Path(tmp) / "full.json"
            empty.write_text(json.dumps({"benchmarks": []}))
            write_results(full, {"a": 1.0})
            with self.assertRaises(ValueError):
                self.compare.compare(empty, full)

    def test_compare_module_is_stdlib_only(self):
        tree = ast.parse((BENCH / "compare.py").read_text())
        allowed = {"argparse", "json", "math", "sys", "pathlib", "__future__"}
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module.split(".")[0])
        self.assertFalse(
            imported - allowed, f"non-stdlib imports: {imported - allowed}"
        )


class ShardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "bench_shard", BENCH / "shard.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.shard = module

    def test_covers_every_benchmark_exactly_once(self):
        names = [f"bench_{i:02d}" for i in range(97)]
        parts = self.shard.shard(names, 8)
        self.assertEqual(len(parts), 8)
        flat = sorted(b for part in parts for b in part)
        self.assertEqual(flat, sorted(names))

    def test_shards_are_balanced_within_one(self):
        parts = self.shard.shard([f"b{i}" for i in range(10)], 3)
        sizes = sorted(len(p) for p in parts)
        self.assertEqual(sizes, [3, 3, 4])

    def test_deterministic_and_deduplicating(self):
        names = ["b", "a", "b", "c"]
        self.assertEqual(self.shard.shard(names, 2), self.shard.shard(names, 2))
        flat = [b for part in self.shard.shard(names, 2) for b in part]
        self.assertEqual(sorted(flat), ["a", "b", "c"])

    def test_rejects_empty_and_oversharded(self):
        with self.assertRaises(ValueError):
            self.shard.shard([], 4)
        with self.assertRaises(ValueError):
            self.shard.shard(["a"], 2)
        with self.assertRaises(ValueError):
            self.shard.shard(["a"], 0)

    def test_exclude_leaves_out_named_benchmarks(self):
        import io
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as tmp:
            names = Path(tmp) / "names.txt"
            names.write_text("a\nb\nc\n")
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.shard.main([str(names), "--shards", "2",
                                 "--exclude", "b"])
            self.assertEqual(buf.getvalue(), "a\nc\n")

    def test_shard_module_is_stdlib_only(self):
        tree = ast.parse((BENCH / "shard.py").read_text())
        allowed = {"argparse", "sys", "__future__"}
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module.split(".")[0])
        self.assertFalse(
            imported - allowed, f"non-stdlib imports: {imported - allowed}"
        )


class PinTests(unittest.TestCase):
    def test_base_image_matches_sealed_build_image(self):
        dockerfile = (BENCH / "Dockerfile").read_text()
        main = (ROOT / "Dockerfile").read_text()
        digest = re.search(r"alpine:3\.24\.1@sha256:[0-9a-f]{64}", main)
        self.assertIsNotNone(digest, "main Dockerfile has no pinned alpine image")
        self.assertIn(digest.group(0), dockerfile)

    def test_pbs_reference_matches_sources_lock(self):
        import sys

        sys.path.insert(0, str(ROOT))
        from buildsys.inputs import load_lock

        lock = {e.name: e for e in load_lock(ROOT / "sources.lock.json")}
        dockerfile = (BENCH / "Dockerfile").read_text()
        self.assertIn(lock["reference-pbs"].url, dockerfile)
        self.assertIn(lock["reference-pbs"].sha256, dockerfile)

    def test_run_single_pins_pyperformance_and_rigorous_flags(self):
        script = (BENCH / "run_single.sh").read_text()
        self.assertIn("pyperformance==1.14.0", script)
        self.assertIn("--rigorous", script)
        self.assertIn("--warmups 2", script)

    def test_run_single_installs_offline_from_vendor(self):
        script = (BENCH / "run_single.sh").read_text()
        self.assertIn("--no-index", script)
        self.assertIn("--find-links /bench/vendor", script)
        self.assertNotIn("pypi", script.lower())

    def test_vendor_wheels_match_recorded_hashes(self):
        vendor = BENCH / "vendor"
        sums = (vendor / "SHA256SUMS").read_text().splitlines()
        self.assertTrue(sums, "vendor/SHA256SUMS is empty")
        import hashlib

        for line in sums:
            digest, name = line.split()
            blob = vendor / name
            self.assertTrue(blob.is_file(), f"vendored wheel missing: {name}")
            self.assertEqual(hashlib.sha256(blob.read_bytes()).hexdigest(), digest)

    def test_vendor_covers_pyperformance_closure(self):
        wheels = {p.name for p in (BENCH / "vendor").glob("*.whl")}
        self.assertTrue(
            any(n.startswith("pyperformance-1.14.0-") for n in wheels)
        )
        for prefix in ("pyperf-", "psutil-", "packaging-"):
            self.assertTrue(
                any(n.startswith(prefix) for n in wheels), prefix
            )

    def test_dockerfile_copies_vendor_and_verifies_hashes(self):
        dockerfile = (BENCH / "Dockerfile").read_text()
        self.assertIn("COPY vendor/ /bench/vendor/", dockerfile)
        self.assertIn("sha256sum -c SHA256SUMS", dockerfile)

    def test_run_parallel_merges_per_side(self):
        script = (BENCH / "run_parallel.sh").read_text()
        self.assertIn("pool.py", script)
        self.assertIn("shard.py", script)
        self.assertIn("--affinity", (BENCH / "run_single.sh").read_text())

    def test_run_parallel_prewarms_worker_venvs(self):
        script = (BENCH / "run_parallel.sh").read_text()
        self.assertIn("warmup", script)

    def test_run_parallel_serializes_fixed_port_benchmarks(self):
        script = (BENCH / "run_parallel.sh").read_text()
        for bench in ("asyncio_tcp", "asyncio_tcp_ssl", "asyncio_websockets"):
            self.assertIn(bench, script)
        self.assertIn("--exclude", script)

    def test_cpu_assignment_interleaves_sides(self):
        script = (BENCH / "run_benchmarks.sh").read_text()
        self.assertIn("seq 0 2", script)
        self.assertIn("seq 1 2", script)


class PoolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "bench_pool", BENCH / "pool.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.pool = module

    def write(self, path: Path, benches: dict[str, list[list[float]]]) -> None:
        path.write_text(json.dumps({
            "benchmarks": [
                {"metadata": {"name": n}, "runs": [{"values": v} for v in runs]}
                for n, runs in benches.items()
            ],
        }))

    def test_pools_values_across_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            self.write(tmpdir / "s1.json", {"a": [[1.0, 1.0]], "b": [[2.0]]})
            self.write(tmpdir / "s2.json", {"a": [[3.0]], "c": [[4.0]]})
            suite = self.pool.pool([tmpdir / "s1.json", tmpdir / "s2.json"])
            by_name = {b["metadata"]["name"]: b for b in suite["benchmarks"]}
            self.assertEqual(sorted(by_name), ["a", "b", "c"])
            values = [v for r in by_name["a"]["runs"] for v in r["values"]]
            self.assertEqual(sorted(values), [1.0, 1.0, 3.0])

    def test_pool_round_trips_through_compare(self):
        compare = load_compare_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            self.write(tmpdir / "p1.json", {"a": [[1.0, 1.0]]})
            self.write(tmpdir / "p2.json", {"a": [[1.0]]})
            self.write(tmpdir / "o1.json", {"a": [[1.005, 1.005]]})
            pooled_pbs = tmpdir / "pbs.json"
            pooled_ours = tmpdir / "ours.json"
            self.assertEqual(
                self.pool.main([str(pooled_pbs), str(tmpdir / "p1.json"),
                                str(tmpdir / "p2.json")]), 0)
            self.assertEqual(
                self.pool.main([str(pooled_ours), str(tmpdir / "o1.json")]), 0)
            report = compare.compare(pooled_pbs, pooled_ours)
            self.assertAlmostEqual(report["geomean_ours_over_pbs"], 1.005)
            self.assertTrue(report["pass"])

    def test_single_benchmark_shape_uses_top_level_name(self):
        compare = load_compare_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "single.json"
            path.write_text(json.dumps({
                "metadata": {"name": "python_startup"},
                "benchmarks": [{"runs": [{"values": [0.007, 0.007]}]}],
            }))
            self.assertAlmostEqual(
                compare.load_means(path)["python_startup"], 0.007)

    def test_pool_normalizes_top_level_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            (tmpdir / "s1.json").write_text(json.dumps({
                "metadata": {"name": "python_startup"},
                "benchmarks": [{"runs": [{"values": [0.007]}]}],
            }))
            (tmpdir / "s2.json").write_text(json.dumps({
                "metadata": {"name": "json_loads"},
                "benchmarks": [{"runs": [{"values": [0.05]}]}],
            }))
            suite = self.pool.pool([tmpdir / "s1.json", tmpdir / "s2.json"])
            by_name = {b["metadata"]["name"]: b for b in suite["benchmarks"]}
            self.assertEqual(sorted(by_name), ["json_loads", "python_startup"])

    def test_pool_rejects_empty_input(self):
        with self.assertRaises(ValueError):
            self.pool.pool([])
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty.json"
            empty.write_text(json.dumps({"benchmarks": []}))
            with self.assertRaises(ValueError):
                self.pool.pool([empty])

    def test_pool_module_is_stdlib_only(self):
        tree = ast.parse((BENCH / "pool.py").read_text())
        allowed = {"argparse", "json", "sys", "pathlib", "__future__"}
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module.split(".")[0])
        self.assertFalse(
            imported - allowed, f"non-stdlib imports: {imported - allowed}"
        )

    def test_run_suite_covers_both_interpreters(self):
        script = (BENCH / "run_suite.sh").read_text()
        self.assertIn("/bench/pbs/python/bin/python3.14", script)
        self.assertIn("/bench/ours/python/bin/python3.14", script)
        self.assertIn("3, 14, 6", script)


if __name__ == "__main__":
    unittest.main()
