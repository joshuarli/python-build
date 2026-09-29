"""Contract tests for the lane's perf harness: verdicts, sync plans, leases.

These tests use synthetic summaries and scratch trees. They build nothing,
run no benchmarks, and never touch the real host lease.
"""

from __future__ import annotations

import fcntl
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

LANE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LANE))

import perf  # noqa: E402
import perf_verdict as pv  # noqa: E402


def summary(wall_ci, *, wall_ratios=(1.0, 1.0, 1.0), cpu=None, status="pass", memory=None):
    timing = {"paired_ratio_samples": list(wall_ratios), "median_ratio_ci95": wall_ci,
              "status": status}
    if cpu is not None:
        base, cand = cpu
        timing["cpu"] = {"status": "compared", "metrics": {"total_seconds_per_operation": {
            "baseline_samples": list(base), "candidate_samples": list(cand)}}}
    return {"comparison": {"timing": timing, "memory": {"metrics": memory or {}}}}


def verdict(*runs):
    return pv.entity_verdict([pv.run_observation(item) for item in runs])


def sample(cpu, load=0, peak=0, digest="d"):
    return {"cpu_seconds_per_iteration": cpu, "load_footprint_bytes": load,
            "working_peak_bytes": peak, "digest": digest}


def module(base, cand):
    return pv.module_observation(base, cand)


class ClassifyTests(unittest.TestCase):
    def test_interval_must_clear_the_practical_floor(self):
        self.assertEqual(pv.classify([0.95, 0.98]), "better")
        self.assertEqual(pv.classify([0.97, 0.995]), "neutral")
        self.assertEqual(pv.classify([1.02, 1.05]), "worse")
        self.assertEqual(pv.classify([1.001, 1.009]), "neutral")
        self.assertEqual(pv.classify(None), "insufficient")

    def test_claims_need_every_run_to_agree(self):
        self.assertEqual(pv.replicate(["better", "better"]), "improved")
        self.assertEqual(pv.replicate(["better", "neutral"]), "neutral")
        self.assertEqual(pv.replicate(["worse", "worse"]), "regressed")
        self.assertEqual(pv.replicate(["better", "worse"]), "unstable")
        self.assertEqual(pv.replicate(["better", "insufficient"]), "insufficient")

    def test_harness_timing_failure_counts_as_worse(self):
        observation = pv.run_observation(summary([0.99, 1.009], status="fail"))
        self.assertEqual(observation["metrics"]["wall"]["class"], "worse")

    def test_cpu_uses_paired_bootstrap(self):
        observation = pv.run_observation(summary(
            [0.99, 1.0], cpu=([1.0, 1.0, 1.0, 1.0, 1.0], [0.9, 0.91, 0.9, 0.89, 0.9])))
        self.assertEqual(observation["metrics"]["cpu"]["class"], "better")

    def test_memory_needs_floor_and_noise(self):
        grown = {"peak_rss": {"ratio_candidate_over_baseline": 1.05, "absolute_change": 5e6,
                              "noise_allowance": 1e6, "status": "fail"}}
        within = {"peak_rss": {"ratio_candidate_over_baseline": 1.05, "absolute_change": 5e5,
                               "noise_allowance": 1e6, "status": "pass"}}
        self.assertEqual(pv.run_observation(summary([0.99, 1.0], memory=grown))["metrics"]["peak_rss"]["class"],
                         "worse")
        self.assertEqual(pv.run_observation(summary([0.99, 1.0], memory=within))["metrics"]["peak_rss"]["class"],
                         "neutral")


class DecideTests(unittest.TestCase):
    def test_replicated_target_win_is_accepted(self):
        workloads = {"zlib_decode_1m": verdict(summary([0.90, 0.95]), summary([0.91, 0.96])),
                     "python_startup": verdict(summary([0.99, 1.01]), summary([0.99, 1.005]))}
        decision = pv.decide(workloads, targets=["zlib_decode_1m"], runs=2, quiet=True, gate=True)
        self.assertEqual(decision["decision"], pv.ACCEPT)
        self.assertEqual(decision["improved"], ["zlib_decode_1m wall"])

    def test_replicated_guard_regression_rejects_a_win(self):
        workloads = {"zlib_decode_1m": verdict(summary([0.90, 0.95]), summary([0.91, 0.96])),
                     "python_startup": verdict(summary([1.03, 1.05]), summary([1.02, 1.04]))}
        decision = pv.decide(workloads, targets=["zlib_decode_1m"], runs=2, quiet=True, gate=True)
        self.assertEqual(decision["decision"], pv.REJECT)
        self.assertEqual(decision["regressions"], ["python_startup wall"])

    def test_single_run_regression_does_not_reject(self):
        workloads = {"zlib_decode_1m": verdict(summary([0.90, 0.95]), summary([0.91, 0.96])),
                     "python_startup": verdict(summary([1.03, 1.05]), summary([0.99, 1.01]))}
        decision = pv.decide(workloads, targets=["zlib_decode_1m"], runs=2, quiet=True, gate=True)
        self.assertEqual(decision["decision"], pv.ACCEPT)

    def test_gate_needs_two_runs_and_a_quiet_host(self):
        one = {"zlib_decode_1m": verdict(summary([0.90, 0.95]))}
        self.assertEqual(pv.decide(one, targets=["zlib_decode_1m"], runs=1, quiet=True,
                                   gate=True)["decision"], pv.INCONCLUSIVE)
        self.assertEqual(pv.decide(one, targets=["zlib_decode_1m"], runs=1, quiet=True,
                                   gate=False)["decision"], pv.ACCEPT)
        self.assertEqual(pv.decide(one, targets=["zlib_decode_1m"], runs=1, quiet=False,
                                   gate=False)["decision"], pv.INCONCLUSIVE)

    def test_unstable_and_neutral(self):
        unstable = {"w": verdict(summary([0.90, 0.95]), summary([1.03, 1.05]))}
        self.assertEqual(pv.decide(unstable, targets=["w"], runs=2, quiet=True, gate=True)["decision"],
                         pv.INCONCLUSIVE)
        neutral = {"w": verdict(summary([0.98, 1.01]), summary([0.985, 1.0]))}
        self.assertEqual(pv.decide(neutral, targets=["w"], runs=2, quiet=True, gate=True)["decision"],
                         pv.NEUTRAL)

    def test_calibration_flags_any_difference(self):
        clean = {"w": verdict(summary([0.99, 1.01]), summary([0.995, 1.004]))}
        self.assertEqual(pv.calibration(clean, runs=2, quiet=True, gate=True)["decision"], "CALIBRATION-OK")
        biased = {"w": verdict(summary([0.95, 0.98]), summary([0.96, 0.98]))}
        self.assertEqual(pv.calibration(biased, runs=2, quiet=True, gate=True)["decision"],
                         "CALIBRATION-FAILED")
        self.assertEqual(pv.calibration(clean, runs=2, quiet=False, gate=True)["decision"],
                         "CALIBRATION-INCONCLUSIVE")

    def test_render_marks_targets_and_decision(self):
        workloads = {"w": verdict(summary([0.90, 0.95], wall_ratios=(0.92, 0.93, 0.94)))}
        text = pv.render(workloads, pv.decide(workloads, targets=["w"], runs=1, quiet=True, gate=False))
        self.assertIn("*w ", text)
        self.assertIn("DECISION: ACCEPT (explore", text)


class ModuleTests(unittest.TestCase):
    def test_module_metrics_pair_by_round_with_memory_floors(self):
        base = [sample(1.0, 100_000, 0), sample(1.0, 100_000, 0), sample(1.0, 100_000, 0)]
        cand = [sample(2.0, 400_000, 10_000), sample(2.1, 400_000, 10_000), sample(1.9, 400_000, 10_000)]
        observation = module(base, cand)
        self.assertEqual(observation["metrics"]["cpu"]["class"], "worse")
        self.assertEqual(observation["metrics"]["load_footprint"]["class"], "worse")
        # Both working peaks sit below the 256 KiB floor: equal, not infinite.
        self.assertEqual(observation["metrics"]["working_peak"]["ratios"], [1.0, 1.0, 1.0])
        self.assertFalse(observation["mismatch"])

    def test_digest_disagreement_is_a_mismatch_and_rejects(self):
        observation = module([sample(1.0, digest="a")], [sample(1.0, digest="b")])
        self.assertTrue(observation["mismatch"])
        entities = {"json": pv.entity_verdict([observation])}
        decision = pv.decide(entities, targets=["json"], runs=1, quiet=True, gate=False)
        self.assertEqual(decision["decision"], pv.REJECT)
        self.assertEqual(pv.goal_status(entities["json"])["status"], "MISMATCH")

    def test_known_mismatch_is_reported_not_rejected(self):
        entities = {"compileall_source": pv.entity_verdict([pv.mismatch_observation("workload")]),
                    "w": verdict(summary([0.90, 0.95]))}
        decision = pv.decide(entities, targets=["w"], runs=1, quiet=True, gate=False,
                             known_mismatches=["compileall_source"])
        self.assertEqual(decision["decision"], pv.ACCEPT)
        self.assertIn("documented output differences", " ".join(decision["reasons"]))

    def test_module_target_improves_on_cpu(self):
        runs = [module([sample(1.0)] * 5, [sample(0.8), sample(0.82), sample(0.79), sample(0.81), sample(0.8)])
                for _ in range(2)]
        entities = {"json": pv.entity_verdict(runs)}
        decision = pv.decide(entities, targets=["json"], runs=2, quiet=True, gate=True)
        self.assertEqual(decision["decision"], pv.ACCEPT)
        self.assertEqual(decision["improved"], ["json cpu"])


class GoalTests(unittest.TestCase):
    def _goal(self, ratios):
        runs = [module([sample(1.0, 1 << 20, 1 << 20)] * 5,
                       [sample(value, 1 << 20, 1 << 20) for value in ratios]) for _ in range(2)]
        return pv.goal_status(pv.entity_verdict(runs))

    def test_band(self):
        self.assertEqual(self._goal([2.0, 2.1, 1.9, 2.0, 2.05])["status"], "OVER")
        self.assertEqual(self._goal([0.95, 0.96, 0.94, 0.95, 0.97])["status"], "MET")
        self.assertEqual(self._goal([1.0, 1.0, 1.0, 1.0, 1.0])["status"], "MET")
        # CPU provably under 0.9x, but memory at parity: the module is MET.
        self.assertEqual(self._goal([0.5, 0.52, 0.49, 0.5, 0.51])["status"], "MET")
        self.assertEqual(self._goal([0.5, 0.52, 0.49, 0.5, 0.51])["metrics"]["cpu"], "BEYOND")
        self.assertEqual(self._goal([1.02, 1.3, 0.99, 1.2, 1.01])["status"], "UNCLEAR")


class IncrementalPlanTests(unittest.TestCase):
    def test_changed_removed_and_clean_only(self):
        plan = perf.incremental_plan(
            {"Modules/_json_rs/src/lib.rs": b"new", "Lib/json/__init__.py": b"same",
             "Modules/Setup.local": b"changed", "Makefile.pre.in": b"same"},
            {"Modules/_json_rs/src/lib.rs": b"old", "Lib/json/__init__.py": b"same",
             "Modules/Setup.local": b"before", "Makefile.pre.in": b"same"},
            ["Modules/_json_rs/src/lib.rs", "Lib/json/__init__.py", "Modules/Setup.local",
             "Makefile.pre.in", "Modules/_gone_rs/src/lib.rs"],
        )
        self.assertEqual(plan["changed"], ["Modules/Setup.local", "Modules/_json_rs/src/lib.rs"])
        self.assertEqual(plan["removed"], ["Modules/_gone_rs/src/lib.rs"])
        self.assertEqual(plan["clean_only"], ["Modules/Setup.local"])

    def test_new_file_is_a_change(self):
        plan = perf.incremental_plan({"Lib/new.py": b"x"}, {"Lib/new.py": None}, [])
        self.assertEqual(plan, {"changed": ["Lib/new.py"], "removed": [], "clean_only": []})


class TreeAndArtifactTests(unittest.TestCase):
    def test_tree_digest_tracks_bytes_modes_and_links(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "bin").mkdir()
            (root / "bin" / "python3.16").write_bytes(b"a")
            first = perf.tree_digest(root)["sha256"]
            (root / "bin" / "python3.16").chmod(0o755)
            second = perf.tree_digest(root)["sha256"]
            (root / "bin" / "python3").symlink_to("python3.16")
            third = perf.tree_digest(root)["sha256"]
            self.assertEqual(len({first, second, third}), 3)

    def _layout(self, root: Path, *, installed: bytes, release: bytes, debug: bool) -> tuple[Path, Path]:
        build = root / "build"
        out = build / "target" / perf.lb.TARGET / "release" / "build" / "_json_rs" / "x" / "out"
        out.mkdir(parents=True)
        (out / "lib_json_rs.dylib").write_bytes(release)
        if debug:
            (build / "target" / perf.lb.TARGET / "debug").mkdir()
        dynload = root / "stage" / "lib" / "python3.16" / "lib-dynload"
        dynload.mkdir(parents=True)
        (dynload / "_json_rs.cpython-316-darwin.so").write_bytes(installed)
        (dynload / "math.cpython-316-darwin.so").write_bytes(b"c extension")
        return build, root / "stage"

    def test_release_artifact_is_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            build, stage = self._layout(Path(temp), installed=b"rel", release=b"rel", debug=False)
            found = perf.verify_release_artifacts(build, stage, {"_json_rs", "cpython-sys"})
            self.assertEqual(set(found), {"_json_rs"})

    def test_debug_artifact_or_tree_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            build, stage = self._layout(Path(temp), installed=b"dbg", release=b"rel", debug=False)
            with self.assertRaisesRegex(perf.LaneError, "release-profile"):
                perf.verify_release_artifacts(build, stage, {"_json_rs"})
        with tempfile.TemporaryDirectory() as temp:
            build, stage = self._layout(Path(temp), installed=b"rel", release=b"rel", debug=True)
            with self.assertRaisesRegex(perf.LaneError, "dev-profile"):
                perf.verify_release_artifacts(build, stage, {"_json_rs"})


class LeaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher = mock.patch.object(perf, "_lease_dir", return_value=Path(self.temp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _try(self, name: str, operation: int) -> bool:
        with (Path(self.temp.name) / name).open("a+") as handle:
            try:
                fcntl.flock(handle, operation | fcntl.LOCK_NB)
            except BlockingIOError:
                return False
            fcntl.flock(handle, fcntl.LOCK_UN)
            return True

    def test_builds_share_and_block_measurement(self):
        with perf.host_lease("build", "build a"):
            self.assertTrue(self._try("host.lock", fcntl.LOCK_SH))
            self.assertFalse(self._try("host.lock", fcntl.LOCK_EX))
            self.assertTrue(self._try("turnstile.lock", fcntl.LOCK_EX))
            self.assertEqual([item["what"] for item in perf.lease_holders()], ["build a"])
        self.assertEqual(perf.lease_holders(), [])

    def test_measurement_is_exclusive_and_closes_the_turnstile(self):
        with perf.host_lease("measure", "bench"):
            self.assertFalse(self._try("host.lock", fcntl.LOCK_SH))
            self.assertFalse(self._try("turnstile.lock", fcntl.LOCK_EX))
        self.assertTrue(self._try("host.lock", fcntl.LOCK_EX))


class SelectionTests(unittest.TestCase):
    def test_gate_adds_guards_and_rejects_unavailable_inputs(self):
        targets, workloads, modules = perf.selection(workloads=["zlib_stream_4k"], modules=["json"], gate=True)
        self.assertEqual(targets, ["json", "zlib_stream_4k"])
        self.assertEqual(workloads, ["zlib_stream_4k", *perf.GATE_WORKLOADS])
        self.assertEqual(modules, ["json"])
        with self.assertRaisesRegex(perf.LaneError, "does not lock"):
            perf.selection(workloads=["pylint_source"], modules=[], gate=False)
        with self.assertRaisesRegex(perf.LaneError, "unknown module"):
            perf.selection(workloads=[], modules=["nosuch"], gate=False)
        with self.assertRaisesRegex(perf.LaneError, "select"):
            perf.selection(workloads=[], modules=[], gate=False)

    def test_every_checklist_route_has_a_kernel(self):
        text = (LANE.parent / "rust-for-cpython.md").read_text()
        import re
        routes = re.findall(r"^- \[x\] `([^`]+)`", text, re.M)
        self.assertEqual(len(routes), 71)
        self.assertEqual(sorted(routes), sorted(perf.module_routes()))


if __name__ == "__main__":
    unittest.main()
