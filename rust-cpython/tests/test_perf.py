"""Contract tests for the lane's perf harness: verdicts, sync plans, leases.

These tests use synthetic summaries and scratch trees. They build nothing,
run no benchmarks, and never touch the real host lease.
"""

from __future__ import annotations

import fcntl
from contextlib import ExitStack, nullcontext
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

LANE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LANE))

import perf  # noqa: E402
import perf_verdict as pv  # noqa: E402
import builtin_modules  # noqa: E402


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


class ExploratoryEarlyRejectionTests(unittest.TestCase):
    def measure(self, classes=("worse", "worse"), *, bad_module=False, mismatch=False,
                guard_error=None, harness_changed=False, sampling_error=None, **options):
        with tempfile.TemporaryDirectory() as temp, ExitStack() as patches:
            root = Path(temp)
            sides = {ref: {"ref": ref, "name": ref[1:], "stage": root / ref[1:],
                           "python": Path("/python"), "report": {}}
                     for ref in ("@control", "@incumbent")}
            calls = []
            counts = {}
            def observation(name, kind):
                counts[name] = counts.get(name, 0) + 1
                bad = name == ("json" if bad_module else "first")
                cls = classes[counts[name] - 1] if bad else "neutral"
                ratio = {"worse": 1.2, "better": 0.8, "neutral": 1.0}[cls]
                metrics = {metric: {"class": cls, "ratios": [ratio] * 3,
                                    "ci95": [ratio, ratio]}
                           for metric in (("load_footprint", "working_peak")
                                          if kind == "module" else ("peak_rss",))}
                metrics["cpu"] = {"class": "worse", "ratios": [2.0] * 3,
                                  "ci95": [2.0, 2.0]}
                return {"kind": kind, "metrics": metrics,
                        "mismatch": mismatch and name == "tail"}
            def workload(baseline, candidate, name, **kwargs):
                calls.append(("workload", name))
                if sampling_error == "workload":
                    raise perf.LaneError("workload failed")
                return observation(name, "workload")
            def module(baseline, candidate, name, **kwargs):
                self.assertEqual(kwargs["rounds"], 5)
                self.assertEqual(kwargs["iterations"], 37)
                calls.append(("module", name))
                if sampling_error == "module":
                    raise perf.LaneError("module failed")
                return observation(name, "module")
            def patch(name, **kwargs):
                return patches.enter_context(mock.patch.object(perf, name, **kwargs))
            patch("LANE", new=root)
            identity = {"source_sha256": "fixture"}
            patch("_harness_identity", side_effect=[identity, identity,
                  {"source_sha256": "changed"} if harness_changed else identity])
            patch("selection", return_value=(["first", "tail", "json", "csv"],
                                              ["first", "tail"], ["json", "csv"]))
            patch("host_lease", return_value=nullcontext())
            patch("resolve", side_effect=sides.__getitem__)
            checks = patch("_verify_stage", side_effect=guard_error)
            gates = patch("_gate_checks")
            patch("_host_sample", return_value={"quiet": True})
            patch("_module_iterations", return_value=37,
                  side_effect=perf.LaneError("iterations failed")
                  if sampling_error == "iterations" else None)
            patch("_run_bench", side_effect=workload)
            patch("_measure_module", side_effect=module)
            patches.enter_context(mock.patch.object(pv, "run_observation", side_effect=lambda x, **kw: x))
            arguments = dict(baseline_ref="@incumbent", candidate_ref="@control",
                             workloads=["first", "tail"], modules=["json", "csv"], gate=False,
                             runs=len(classes), profile="standard", timing_only=False, min_idle=0,
                             self_compare=False, record_baselines=False, memory_only=True)
            arguments.update(options)
            try:
                record = perf._measure(**arguments)
            finally:
                self.assertFalse(list(root.glob("results/perf-bench/*/tmp")))
            self.assertEqual(checks.call_count, 2 if arguments["self_compare"] else 4)
            self.assertEqual(gates.call_count, int(arguments["gate"]))
            saved = json.loads((Path(record["directory"]) / "verdict.json").read_text())
            self.assertEqual(saved, record)
            return record, calls

    def test_replicated_workload_regression_stops_remaining_calls_and_retains_raw(self):
        record, calls = self.measure(mismatch=True)
        self.assertEqual(calls, [("workload", "first"), ("workload", "tail"),
                                 ("module", "json"), ("module", "csv"), ("workload", "first")])
        self.assertEqual(record["decision"]["decision"], pv.REJECT)
        self.assertFalse(record["sampling_complete"])
        self.assertEqual(record["incomplete_entities"], ["tail", "json", "csv"])
        self.assertEqual(record["stopped_after"], {"run": 2, "entity": "first"})
        self.assertEqual(list(record["entities"]), ["first"])
        self.assertEqual(len(record["raw"]["first"]), 2)
        self.assertTrue(record["raw"]["tail"][0]["mismatch"])
        self.assertEqual(record["decision"]["mismatches"], ["tail"])

    def test_control_comparison_omits_incomplete_absolute_goals(self):
        record, calls = self.measure(baseline_ref="@control", candidate_ref="@incumbent")
        self.assertEqual(record["decision"]["decision"], pv.REJECT)
        self.assertEqual(record["goals"], {})
        self.assertEqual(record["incomplete_entities"], ["tail", "json", "csv"])
        record, calls = self.measure(bad_module=True, baseline_ref="@control",
                                     candidate_ref="@incumbent")
        self.assertEqual(record["decision"]["decision"], pv.REJECT)
        self.assertEqual(set(record["goals"]), {"json"})

    def test_output_mismatch_without_regression_retains_complete_checks(self):
        record, calls = self.measure(("neutral", "neutral"), mismatch=True)
        self.assertEqual(len(calls), 8)
        self.assertTrue(record["sampling_complete"])
        self.assertEqual(record["decision"]["decision"], pv.REJECT)
        self.assertEqual(record["decision"]["mismatches"], ["tail"])

    def test_replicated_module_regression_stops_module_tail(self):
        record, calls = self.measure(bad_module=True)
        self.assertEqual(calls[-1], ("module", "json"))
        self.assertEqual(len(calls), 7)
        self.assertEqual(record["incomplete_entities"], ["csv"])

    def test_one_worse_then_neutral_keeps_complete_evidence(self):
        record, calls = self.measure(("worse", "neutral"))
        self.assertEqual(len(calls), 8)
        self.assertTrue(record["sampling_complete"])
        self.assertEqual(record["decision"]["regressions"], [])
        self.assertIsNone(record["stopped_after"])

    def test_three_runs_require_all_three_regressions(self):
        record, calls = self.measure(("worse", "worse", "worse"))
        self.assertEqual(len(calls), 9)
        self.assertEqual(record["stopped_after"]["run"], 3)
        record, calls = self.measure(("worse", "worse", "neutral"))
        self.assertEqual(len(calls), 12)
        self.assertTrue(record["sampling_complete"])

    def test_timing_regression_does_not_stop_memory_survivors(self):
        for classes in (("neutral", "neutral"), ("better", "better")):
            with self.subTest(classes=classes):
                record, calls = self.measure(classes)
                self.assertEqual(len(calls), 8)
                self.assertTrue(record["sampling_complete"])
                self.assertEqual(record["decision"]["regressions"], [])

    def test_nonexploratory_modes_and_single_run_keep_full_sampling(self):
        for options in ({"gate": True}, {"self_compare": True}, {"slug_prefix": "goals-"},
                        {"record_baselines": True}, {"memory_only": False}):
            with self.subTest(options=options):
                record, calls = self.measure(**options)
                self.assertEqual(len(calls), 8)
                self.assertTrue(record["sampling_complete"])
        record, calls = self.measure(("worse",))
        self.assertEqual(len(calls), 4)
        self.assertTrue(record["sampling_complete"])

    def test_iteration_and_sampling_errors_remove_scratch(self):
        for operation in ("iterations", "workload", "module"):
            with self.subTest(operation=operation), self.assertRaisesRegex(
                    perf.LaneError, operation + " failed"):
                self.measure(sampling_error=operation)

    def test_final_stage_and_harness_errors_are_not_hidden_by_early_rejection(self):
        with self.assertRaisesRegex(perf.LaneError, "stage changed"):
            self.measure(guard_error=[None, None, perf.LaneError("stage changed")])
        with self.assertRaisesRegex(perf.LaneError, "harness changed"):
            self.measure(harness_changed=True)


class WorkloadProfileTests(unittest.TestCase):
    def test_matched_executable_requires_matched_homes_before_resolving(self):
        with mock.patch.object(perf, "resolve") as resolve, self.assertRaisesRegex(
                perf.LaneError, "requires --matched-prefix"):
            perf.bench(baseline_ref="@control", candidate_ref="@incumbent", workloads=[],
                       gate=False, runs=2, profile="standard", timing_only=False,
                       min_idle=0, memory_only=True, matched_executable=True)
        resolve.assert_not_called()

    def test_module_launch_alias_preserves_verified_identity_and_checks_observed_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            stage = Path(temp) / "stage"
            python = stage / "bin/python3.16"
            python.parent.mkdir(parents=True)
            python.write_text("fixture")
            home = Path(temp) / "home"
            home.symlink_to(stage, target_is_directory=True)
            launch = home / "bin/python3.16"
            observation = {"digest": "same", "runtime_executable": str(launch),
                           "runtime_base_executable": str(launch),
                           "runtime_prefix": str(home), "runtime_exec_prefix": str(home)}
            with mock.patch.object(perf.subprocess, "run", return_value=mock.Mock(
                    returncode=0, stdout=json.dumps(observation), stderr="")) as run:
                self.assertEqual(perf._module_sample(
                    python, "collections", 56, Path(temp), runtime_home=home,
                    runtime_executable=launch), observation)
                self.assertEqual(run.call_args.args[0][0], str(launch))
                observation["runtime_base_executable"] = str(python)
                run.return_value.stdout = json.dumps(observation)
                with self.assertRaisesRegex(perf.LaneError, "requested launch"):
                    perf._module_sample(python, "collections", 56, Path(temp),
                                        runtime_home=home, runtime_executable=launch)
            wrong_home = Path(temp) / "other-home"
            wrong_home.symlink_to(stage, target_is_directory=True)
            with mock.patch.object(perf.subprocess, "run") as run, self.assertRaises(perf.LaneError):
                perf._module_sample(python, "collections", 56, Path(temp),
                                    runtime_home=wrong_home, runtime_executable=launch)
            run.assert_not_called()
            home.unlink()
            home.symlink_to(Path(temp) / "other", target_is_directory=True)
            with mock.patch.object(perf.subprocess, "run") as run, self.assertRaises(perf.LaneError):
                perf._module_sample(python, "collections", 56, Path(temp),
                                    runtime_home=home, runtime_executable=launch)
            run.assert_not_called()

    def test_harness_identity_changes_with_source_and_reports_harness_dirty_state(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            lane = repo / "rust-cpython"
            harness = repo / "benchmarks/harness"
            lane.mkdir()
            harness.mkdir(parents=True)
            for name in ("perf.py", "perf_verdict.py", "perf_modules.py"):
                (lane / name).write_text("fixture")
            (repo / "benchmarks/bench.py").write_text("fixture")
            source = harness / "runner.py"
            source.write_text("fixture")
            with mock.patch.object(perf, "LANE", lane), mock.patch.object(perf, "REPO", repo), \
                    mock.patch.object(perf, "_git", side_effect=lambda *args: "commit" if args[0] == "rev-parse" else " M ../benchmarks/harness/runner.py"):
                first = perf._harness_identity()
                source.write_text("changed")
                second = perf._harness_identity()
            self.assertTrue(first["dirty"])
            self.assertNotEqual(first["source_sha256"], second["source_sha256"])
            self.assertNotEqual(first["files"]["benchmarks/harness/runner.py"], second["files"]["benchmarks/harness/runner.py"])

    def test_harness_change_while_waiting_aborts_before_stage_resolution(self):
        with mock.patch.object(perf, "selection", return_value=([], [], [])), \
                mock.patch.object(perf, "host_lease", return_value=nullcontext()), \
                mock.patch.object(perf, "_harness_identity", side_effect=[{"source_sha256": "first"}, {"source_sha256": "changed"}]), \
                mock.patch.object(perf, "resolve") as resolve, \
                self.assertRaisesRegex(perf.LaneError, "changed while waiting"):
            perf._measure(baseline_ref="@control", candidate_ref="@incumbent", workloads=[], modules=[],
                          gate=False, runs=2, profile="quick", timing_only=False, min_idle=0,
                          self_compare=False, record_baselines=False, memory_only=True)
        resolve.assert_not_called()

    def test_matched_calibration_uses_two_homes_for_one_verified_stage(self):
        with tempfile.TemporaryDirectory() as temp:
            stage = Path(temp) / "stage"
            stage.mkdir()
            side = {"ref": "@control", "name": "control", "stage": stage,
                    "python": stage / "bin/python", "report": {"commit": "fixture"}}
            with mock.patch.object(perf, "LANE", Path(temp)), \
                    mock.patch.object(perf, "_harness_identity", return_value={"source_sha256": "fixture"}), \
                    mock.patch.object(perf, "selection", return_value=(["json"], [], ["json"])), \
                    mock.patch.object(perf, "host_lease", return_value=nullcontext()), \
                    mock.patch.object(perf, "resolve", return_value=side), \
                    mock.patch.object(perf, "_verify_stage"), \
                    mock.patch.object(perf, "_module_iterations", return_value=37), \
                    mock.patch.object(perf, "_module_sample", return_value=sample(2.0, 1 << 20, 1 << 20)) as measure:
                record = perf._measure(
                    baseline_ref="@control", candidate_ref="@control", workloads=[], modules=["json"],
                    gate=False, runs=2, profile="quick", timing_only=False, min_idle=0,
                    self_compare=True, record_baselines=False, memory_only=True, matched_prefix=True)
            context = record["runtime_prefix_context"]
            homes = [Path(context[key]) for key in ("baseline_home", "candidate_home")]
            self.assertEqual(context["kind"], "matched-python-home")
            self.assertEqual(len(str(homes[0])), len(str(homes[1])))
            self.assertNotEqual(homes[0], homes[1])
            self.assertEqual({call.kwargs["runtime_home"] for call in measure.call_args_list}, set(homes))
            self.assertTrue(all(not home.exists() for home in homes))
            self.assertTrue(stage.exists())

    def test_matched_executable_calibration_keeps_original_identity_and_launches_both_aliases(self):
        with tempfile.TemporaryDirectory() as temp:
            stage = Path(temp) / "stage"
            python = stage / "bin/python3.16"
            python.parent.mkdir(parents=True)
            python.write_text("fixture")
            side = {"ref": "@control", "name": "control", "stage": stage,
                    "python": python, "report": {"commit": "fixture"}}
            with mock.patch.object(perf, "LANE", Path(temp)), \
                    mock.patch.object(perf, "_harness_identity", return_value={"source_sha256": "fixture"}), \
                    mock.patch.object(perf, "selection", return_value=(["json"], [], ["json"])), \
                    mock.patch.object(perf, "host_lease", return_value=nullcontext()), \
                    mock.patch.object(perf, "resolve", return_value=side), \
                    mock.patch.object(perf, "_verify_stage"), \
                    mock.patch.object(perf, "_module_iterations", return_value=37) as setup, \
                    mock.patch.object(perf, "_module_sample", return_value=sample(2.0, 1 << 20, 1 << 20)) as measure:
                record = perf._measure(
                    baseline_ref="@control", candidate_ref="@control", workloads=[], modules=["json"],
                    gate=False, runs=2, profile="quick", timing_only=False, min_idle=0,
                    self_compare=True, record_baselines=False, memory_only=True,
                    matched_prefix=True, matched_executable=True)
            context = record["runtime_prefix_context"]
            launches = [Path(context[key]) for key in ("baseline_executable", "candidate_executable")]
            self.assertEqual(context["kind"], "matched-python-home-and-executable")
            self.assertEqual(len(str(launches[0])), len(str(launches[1])))
            self.assertNotEqual(launches[0], launches[1])
            self.assertEqual(setup.call_args.kwargs["runtime_executable"], launches[0])
            self.assertEqual({call.kwargs["runtime_executable"] for call in measure.call_args_list}, set(launches))
            self.assertTrue(all(call.args[0] == python for call in measure.call_args_list))
            self.assertEqual(side["python"], python)
            self.assertTrue(all(not launch.exists() for launch in launches))
            self.assertTrue(python.exists())

    def test_module_runtime_home_changes_only_explicit_launch_environment(self):
        with mock.patch.object(perf.subprocess, "run", return_value=mock.Mock(
                returncode=0, stdout='{"digest":"same"}', stderr="")) as run:
            self.assertEqual(perf._module_sample(
                Path("/stage/bin/python"), "collections", 56, Path("/scratch"),
                runtime_home=Path("/matched/home")), {"digest": "same"})
            self.assertEqual(run.call_args.kwargs["env"]["PYTHONHOME"], "/matched/home")
            command = run.call_args.args[0]
            self.assertEqual(command[:3], ["/stage/bin/python", "-s", "-P"])
            self.assertEqual(command[-4:], ["measure", "collections", "--iterations", "56"])

    def test_matched_prefix_requires_memory_only_before_resolving_stages(self):
        with mock.patch.object(perf, "resolve") as resolve, self.assertRaisesRegex(
                perf.LaneError, "requires --memory-only"):
            perf.bench(baseline_ref="@control", candidate_ref="@incumbent", workloads=[],
                       gate=False, runs=2, profile="standard", timing_only=False,
                       min_idle=0, matched_prefix=True)
        resolve.assert_not_called()

    def test_runtime_prefix_aliases_preserve_trees_and_cleanup_after_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            stages = [Path(temp) / "short", Path(temp) / ("long" * 20)]
            for stage in stages:
                stage.mkdir()
                (stage / "marker").write_text("same")
            with self.assertRaisesRegex(RuntimeError, "stop"):
                with perf._runtime_prefix_aliases(*stages) as homes:
                    self.assertEqual(len(str(homes[0])), len(str(homes[1])))
                    self.assertNotEqual(homes[0], homes[1])
                    for home, stage in zip(homes, stages):
                        self.assertEqual(home.resolve(), stage.resolve())
                        self.assertEqual((home / "marker").stat().st_ino,
                                         (stage / "marker").stat().st_ino)
                    raise RuntimeError("stop")
            self.assertTrue(all(not home.exists() for home in homes))
            self.assertTrue(all(stage.exists() for stage in stages))

    def test_importtime_executes_the_selected_workload(self):
        for workload, module in [('serialization_roundtrip', 'extra'),
                                 ('catalog_json_export', 'catalog_json')]:
            with self.subTest(workload=workload), tempfile.TemporaryDirectory() as temp:
                side = {'python': Path('/python'), 'name': 'fixture'}
                with mock.patch.object(perf, 'LANE', Path(temp)), \
                        mock.patch.object(perf, 'resolve', return_value=side), \
                        mock.patch.object(perf, 'host_lease', return_value=nullcontext()), \
                        mock.patch.object(perf.subprocess, 'run') as run:
                    perf.profile(ref='candidate', workload=workload, module=None,
                                 tool='importtime', iterations=1, seconds=1)
                self.assertEqual(run.call_args.args[0], [
                    '/python', '-X', 'importtime', '-m', f'benchmarks.workloads.{module}',
                    workload, '--iterations', '1'])

    def test_workload_memory_only_flag_is_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "python_startup"
            output.mkdir()
            result = {"identity": {"name": "python_startup"}}
            (output / "summary.json").write_text(json.dumps({"workloads": [result]}))
            side = {"python": Path("/python"), "ref": "candidate", "name": "candidate",
                    "report": {"commit": "abcdef"}}
            for memory_only in (False, True):
                with self.subTest(memory_only=memory_only), \
                        mock.patch.object(perf, "_label", return_value="candidate"), \
                        mock.patch.object(perf.subprocess, "run", return_value=mock.Mock(returncode=0)) as run:
                    perf._run_bench(side, side, "python_startup", output=output, profile="standard",
                                    timing_only=False, self_compare=False, record_baseline=None,
                                    memory_only=memory_only)
                    self.assertEqual("--memory-only" in run.call_args.args[0], memory_only)

    def test_rigorous_modules_keep_supported_workload_evidence_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "python_startup"
            output.mkdir()
            result = {"identity": {"name": "python_startup"}}
            (output / "summary.json").write_text(json.dumps({"workloads": [result]}))
            side = {"python": Path("/python"), "ref": "candidate", "name": "candidate",
                    "report": {"commit": "abcdef"}}

            def evidence_runner(command, **kwargs):
                profile = command[command.index("--profile") + 1]
                return mock.Mock(returncode=0 if profile in {"quick", "standard"} else 2)

            with mock.patch.object(perf, "_label", return_value="candidate"), \
                    mock.patch.object(perf.subprocess, "run", side_effect=evidence_runner) as run:
                self.assertEqual(perf._run_bench(
                    side, side, "python_startup", output=output, profile="rigorous",
                    timing_only=False, self_compare=False, record_baseline=None), result)
            command = run.call_args.args[0]
            self.assertEqual(command[command.index("--profile") + 1], "standard")
            self.assertIn("--evidence", command)
            self.assertNotIn("--timing-only", command)
            self.assertEqual(perf.PROFILE_MODULE_ROUNDS["rigorous"], 10)


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
    def test_replicated_workload_rss_win_is_accepted_with_neutral_timing(self):
        memory = {'peak_rss': {'ratio_candidate_over_baseline': 0.90,
                              'absolute_change': -2e6, 'noise_allowance': 1e6,
                              'status': 'pass'}}
        run = summary([0.99, 1.005], cpu=([1.0] * 5, [1.0] * 5), memory=memory)
        entities = {'python_startup': verdict(run, run)}
        decision = pv.decide(entities, targets=['python_startup'], runs=2,
                             quiet=True, gate=True)
        self.assertEqual(decision['decision'], pv.ACCEPT)
        self.assertEqual(decision['improved'], ['python_startup peak_rss'])

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


class MemoryOnlyTests(unittest.TestCase):
    def entities(self, *, cpu=2.0, load=0.8, peak=1.0, digest="d"):
        runs = [module([sample(1.0, 1 << 20, 1 << 20)] * 5,
                       [sample(cpu, int(load * (1 << 20)), int(peak * (1 << 20)), digest)] * 5)
                for _ in range(2)]
        return {"json": pv.entity_verdict(runs)}

    def decision(self, entities, runs=2):
        return pv.decide(entities, targets=["json"], runs=runs, quiet=False,
                         gate=True, memory_only=True)

    def test_memory_win_ignores_cpu_regression_and_busy_host(self):
        decision = self.decision(self.entities())
        self.assertEqual(decision["decision"], pv.ACCEPT)
        self.assertEqual(decision["improved"], ["json load_footprint"])
        self.assertEqual(decision["regressions"], [])
        self.assertEqual(decision["acceptance_policy"], "memory-only")

    def test_cpu_win_cannot_qualify_memory_neutral(self):
        self.assertEqual(self.decision(self.entities(cpu=0.5, load=1.0))["decision"], pv.NEUTRAL)

    def test_memory_guards_and_mismatches_still_reject(self):
        entities = self.entities()
        entities["guard"] = self.entities(load=1.2)["json"]
        self.assertEqual(self.decision(entities)["decision"], pv.REJECT)
        self.assertEqual(self.decision(self.entities(digest="different"))["decision"], pv.REJECT)

    def test_missing_memory_on_guard_and_single_run_are_inconclusive(self):
        entities = self.entities()
        guard = self.entities(load=1.0)["json"]
        del guard["metrics"]["working_peak"]
        entities["guard"] = guard
        self.assertEqual(self.decision(entities)["decision"], pv.INCONCLUSIVE)
        self.assertEqual(self.decision(self.entities(), runs=1)["decision"], pv.INCONCLUSIVE)

    def test_unstable_memory_is_inconclusive(self):
        entities = self.entities()
        entities["json"]["metrics"]["working_peak"]["verdict"] = "unstable"
        self.assertEqual(self.decision(entities)["decision"], pv.INCONCLUSIVE)

    def test_goals_exclude_cpu_and_require_both_memory_metrics(self):
        entity = self.entities()["json"]
        goal = pv.goal_status(entity, memory_only=True)
        self.assertEqual(goal["status"], "MET")
        self.assertEqual(set(goal["metrics"]), {"load_footprint", "working_peak"})
        del entity["metrics"]["working_peak"]
        self.assertEqual(pv.goal_status(entity, memory_only=True)["status"], "UNCLEAR")

    def test_calibration_ignores_timing_but_requires_memory_and_replication(self):
        entities = self.entities(load=1.0)
        self.assertEqual(pv.calibration(entities, runs=2, quiet=False, gate=True,
                                        memory_only=True)["decision"], "CALIBRATION-OK")
        del entities["json"]["metrics"]["working_peak"]
        self.assertEqual(pv.calibration(entities, runs=2, quiet=False, gate=True,
                                        memory_only=True)["decision"], "CALIBRATION-INCONCLUSIVE")

    def test_workload_observation_accepts_memory_without_timing(self):
        memory = {"peak_rss": {"ratio_candidate_over_baseline": 0.8,
                               "absolute_change": -2e6, "noise_allowance": 1e6,
                               "status": "pass"}}
        observation = pv.run_observation({"comparison": {"memory": {"metrics": memory}}},
                                         memory_only=True)
        self.assertEqual(set(observation["metrics"]), {"peak_rss"})
        entities = {"w": pv.entity_verdict([observation] * 2)}
        decision = pv.decide(entities, targets=["w"], runs=2, quiet=False, gate=True,
                             memory_only=True)
        self.assertEqual(decision["decision"], pv.ACCEPT)

    def test_measure_records_policy_and_preserves_sampling_without_host_waits(self):
        with tempfile.TemporaryDirectory() as temp:
            sides = {ref: {"ref": ref, "name": ref[1:], "stage": Path(temp) / ref[1:],
                           "python": Path("/python"), "report": {"commit": "fixture"}}
                     for ref in ("@control", "@incumbent")}
            with mock.patch.object(perf, "LANE", Path(temp)), \
                    mock.patch.object(perf, "_harness_identity", return_value={"source_sha256": "fixture"}), \
                    mock.patch.object(perf, "selection", return_value=(["json"], [], ["json"])), \
                    mock.patch.object(perf, "host_lease", return_value=nullcontext()), \
                    mock.patch.object(perf, "resolve", side_effect=sides.__getitem__), \
                    mock.patch.object(perf, "_verify_stage"), \
                    mock.patch.object(perf, "_host_sample") as host, \
                    mock.patch.object(perf, "_module_iterations", return_value=37) as iterations, \
                    mock.patch.object(perf, "_module_sample", return_value=sample(2.0, 1 << 20, 1 << 20)) as measure:
                record = perf._measure(
                    baseline_ref="@control", candidate_ref="@incumbent", workloads=[], modules=["json"],
                    gate=False, runs=2, profile="quick", timing_only=False, min_idle=90,
                    self_compare=False, record_baselines=False, memory_only=True)
            host.assert_not_called()
            iterations.assert_called_once()
            self.assertEqual(measure.call_count, 2 * 2 * perf.PROFILE_MODULE_ROUNDS["quick"])
            self.assertTrue(all(call.args[2] == 37 for call in measure.call_args_list))
            self.assertEqual(record["host_samples"], [])
            self.assertIsNone(record["decision"]["quiet"])
            self.assertEqual(record["acceptance_policy"], "memory-only")
            self.assertEqual(set(record["entities"]["json"]["metrics"]),
                             {"load_footprint", "working_peak"})
            saved = json.loads((Path(record["directory"]) / "verdict.json").read_text())
            self.assertEqual(saved["decision"]["acceptance_policy"], "memory-only")
            self.assertEqual(saved["goals"]["json"]["status"], "MET")

    def test_known_control_output_difference_remains_exempt_in_memory_only(self):
        entities = self.entities()
        entities["known"] = pv.entity_verdict([pv.mismatch_observation("workload")] * 2)
        decision = pv.decide(entities, targets=["json"], runs=2, quiet=False, gate=True,
                             known_mismatches=["known"], memory_only=True)
        self.assertEqual(decision["decision"], pv.ACCEPT)
        self.assertIn("documented output differences", " ".join(decision["reasons"]))
        entities["unknown"] = pv.entity_verdict([pv.mismatch_observation("workload")] * 2)
        decision = pv.decide(entities, targets=["json"], runs=2, quiet=False, gate=True,
                             known_mismatches=["known"], memory_only=True)
        self.assertEqual(decision["decision"], pv.REJECT)
        self.assertEqual(decision["mismatches"], ["unknown"])

    def test_missing_memory_goal_renders_as_unavailable(self):
        entities = self.entities()
        del entities["json"]["metrics"]["working_peak"]
        goals = {"json": pv.goal_status(entities["json"], memory_only=True)}
        rendered = pv.render_goals(goals, entities)
        self.assertIn("working_peak n/a UNCLEAR", rendered)
        self.assertNotIn("working_peak 0.00x", rendered)

    def test_memory_only_and_timing_only_are_incompatible(self):
        with self.assertRaisesRegex(perf.LaneError, "requires the memory pass"):
            perf.bench(baseline_ref="@control", candidate_ref="@incumbent", workloads=[],
                       gate=False, runs=2, profile="quick", timing_only=True, min_idle=90,
                       memory_only=True)

    def test_cli_passes_memory_policy_for_all_commands(self):
        for command, extra, handler in [
                ("bench", ["--baseline", "@control", "--candidate", "@incumbent"], "bench"),
                ("calibrate", ["--ref", "@incumbent"], "bench"),
                ("goals", [], "goals")]:
            with self.subTest(command=command), mock.patch.object(perf, handler, return_value=0) as call:
                self.assertEqual(perf.main([command, *extra, "--memory-only"]), 0)
                self.assertTrue(call.call_args.kwargs["memory_only"])


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


class BuiltinPreflightTests(unittest.TestCase):
    def source_failure(self, defect, message, *, reaches_fetch=False):
        with tempfile.TemporaryDirectory() as temp, ExitStack() as patches:
            root = Path(temp).resolve()
            source = root / 'source'
            carrier = source / 'Modules/cpython-rust-staticlib'
            carrier.mkdir(parents=True)
            (source / 'Modules/Setup.local').write_text('*static*\n_collections_rs\n')
            declaration = carrier / 'builtin-helpers.json'
            declaration.write_text(json.dumps({'schema': 1, 'helpers': ['_collections_rs']}))
            manifest = carrier / 'Cargo.toml'
            manifest.write_text('[dependencies]\n_collections_rs = { path = "../_collections_rs" }\n')
            (source / 'Cargo.toml').write_text('[profile.release]\npanic = "abort"\n')
            recipe = ('cpython-rust-staticlib: cpython-sys\n'
                      '\t$(CARGO_HOME)/bin/cargo build --lib --locked '
                      '--package cpython-rust-staticlib --profile $(CARGO_PROFILE) '
                      '--message-format=json >$(abs_builddir)/rust-staticlib-artifacts.jsonl\n')
            if defect == 'declaration':
                declaration.unlink()
            elif defect == 'dependency':
                manifest.write_text('[dependencies]\n_collections_rs = { path = "../wrong" }\n')
            elif defect == 'receipt':
                recipe = recipe.split(' --message-format=')[0] + '\n'
            elif defect == 'panic':
                (source / 'Cargo.toml').write_text('[profile.release]\npanic = "unwind"\n')
            elif defect == 'masked-status':
                recipe = recipe.rstrip() + ' || true\n'
            (source / 'Makefile.pre.in').write_text(recipe)
            paths = {'source_parent': root / 'parent', 'overlay_manifest': root / 'manifest.json',
                     'build': root / 'build', 'cargo_log': root / 'cargo.log'}
            patches.enter_context(mock.patch.object(perf.lb, '_toolchain', return_value=(None, None)))
            patches.enter_context(mock.patch.object(perf.lb, '_llvm_ready'))
            patches.enter_context(mock.patch.object(perf, '_git_state', return_value={}))
            patches.enter_context(mock.patch.object(perf, '_common_dir', return_value=root / '.git'))
            patches.enter_context(mock.patch.object(perf, '_git', return_value=str(root / '.git')))
            patches.enter_context(mock.patch.object(perf.lb, '_extract_fresh', return_value=source))
            patches.enter_context(mock.patch.object(perf, '_stage_overlay', return_value=({}, [])))
            patches.enter_context(mock.patch.object(perf.lb, '_environment', return_value={}))
            command = patches.enter_context(mock.patch.object(
                perf.lb, '_require_command', side_effect=AssertionError('external command reached')))
            error = AssertionError if reaches_fetch else perf.LaneError
            with self.assertRaisesRegex(error, message):
                perf._build_locked('fixture', paths, empty_overlay=False, jobs=1,
                                   incremental=False, state={'configured': False})
            if reaches_fetch:
                command.assert_called_once()
                self.assertIn('fetch', command.call_args.args[0])
            else:
                command.assert_not_called()

    def test_missing_declaration_fails_before_fetch(self):
        self.source_failure('declaration', 'no explicit declaration')

    def test_wrong_carrier_dependency_fails_before_fetch(self):
        self.source_failure('dependency', 'outside the declared static carrier')

    def test_missing_genuine_receipt_recipe_fails_before_fetch(self):
        self.source_failure('receipt', 'Cargo JSON receipt')

    def test_non_abort_carrier_fails_before_fetch(self):
        self.source_failure('panic', 'requires abort panic')

    def test_masked_cargo_failure_is_rejected_before_fetch(self):
        self.source_failure('masked-status', 'Cargo JSON receipt')

    def test_valid_source_reaches_fetch_without_claiming_artifact_proof(self):
        self.source_failure(None, 'external command reached', reaches_fetch=True)

    def test_postbuild_verification_still_requires_actual_cargo_receipt(self):
        def read(path, owner):
            if path.name == 'config.c':
                return b''
            self.assertEqual(path.name, 'rust-staticlib-artifacts.jsonl')
            raise builtin_modules.BuiltinArtifactError('actual Cargo receipt missing')
        with mock.patch.object(builtin_modules, 'validate_builtin_source',
                               return_value=['_collections_rs']) as preflight, \
                mock.patch.object(builtin_modules.SourceArtifacts, 'read', side_effect=read):
            with self.assertRaisesRegex(builtin_modules.BuiltinArtifactError,
                                        'actual Cargo receipt missing'):
                builtin_modules.verify_builtin_artifacts(Path('/source'), Path('/build'),
                    Path('/stage'), 'aarch64-apple-darwin', ())
            preflight.assert_called_once()

    def test_routes_outside_existing_declaration_contract_need_no_new_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp).resolve()
            (source / 'Modules').mkdir()
            (source / 'Modules/Setup.local').write_text('*static*\n_typing_rs\n')
            self.assertEqual(builtin_modules.validate_builtin_source(
                source, 'aarch64-apple-darwin', ()), [])
            self.assertEqual(builtin_modules.verify_builtin_artifacts(
                source, source / 'build', source / 'stage', 'aarch64-apple-darwin', ()), {})


class TreeAndArtifactTests(unittest.TestCase):
    def test_built_members_survive_interleaved_cargo_progress(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "build.log"
            log.write_text(
                "CompilingCARGO_TARGET_DIR=/tmp/target make extension\n"
                " _urllib_parse_rs v0.1.0 (/tmp/source)\n"
                "Running `CARGO_PKG_NAME=_urllib_parse_rs /tmp/rustc "
                "--crate-name _urllib_parse_rs --crate-type cdylib src/lib.rs`\n"
                "Running `CARGO_PKG_NAME=_foreign_rs /tmp/rustc "
                "--crate-name _foreign_rs src/lib.rs`\n"
                "Running `CARGO_PKG_NAME=_unbuilt_rs /tmp/rustc "
                "--crate-name build_script_build build.rs`\n"
                "Fresh _json_rs v0.1.0 (/tmp/source)\n"
            )
            self.assertEqual(
                perf._built_members(log, {"_urllib_parse_rs", "_json_rs", "_unbuilt_rs"}),
                ["_json_rs", "_urllib_parse_rs"],
            )

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
