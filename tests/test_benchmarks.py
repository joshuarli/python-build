"""Contract tests for the generic CPython benchmark harness.

These tests use synthetic results and lightweight workload metadata. They do
not launch benchmark suites, Docker, or network operations.
"""

from __future__ import annotations

from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

from benchmarks.bench import _docker_descriptor, main as bench_main
from benchmarks.harness.memory import (
    SmapsRollup,
    SmapsRollupError,
    parse_smaps_rollup,
    sum_rollups,
)
from benchmarks.harness.models import (
    ResultSchemaError,
    result_from_json,
    result_to_json,
)
from benchmarks.harness.runner import (
    PROFILE_ROUNDS,
    workload_command,
    workload_environment,
)
from benchmarks.workloads.registry import WORKLOADS, select_workloads


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks"


class WorkloadRegistryTests(unittest.TestCase):
    def test_realworld_suite_covers_required_application_paths(self):
        names = {workload.name for workload in WORKLOADS}
        self.assertEqual(
            names,
            {
                "django_wsgi_request",
                "django_asgi_request",
                "django_orm_10k",
                "django_template_realistic",
                "pylint_source",
                "pycparser_source",
                "compileall_source",
                "python_startup",
                "import_django",
                "import_app_stack",
                "pip_install_wheelhouse",
                "rust_base64_small",
                "rust_base64_large",
                "serialization_roundtrip",
                "multiprocess_pool",
            },
        )

    def test_each_workload_has_normalizable_operation_counts(self):
        for workload in WORKLOADS:
            with self.subTest(workload=workload.name):
                self.assertGreater(workload.iterations, 0)
                self.assertGreater(workload.allocation_iterations, 0)
                self.assertLessEqual(
                    workload.allocation_iterations, workload.iterations
                )
                self.assertTrue(workload.operation)
                self.assertIn(
                    workload.noise_class,
                    {"stable", "noisy", "diagnostic-only"},
                )

    def test_suite_profile_and_category_select_the_expected_work(self):
        full = select_workloads("full", "standard", None, None)
        self.assertEqual(full, list(WORKLOADS))

        quick = select_workloads("realworld", "quick", None, None)
        self.assertGreater(len(full), len(quick))
        self.assertTrue({item.name for item in quick} <= {item.name for item in full})

        django = select_workloads("realworld", "standard", None, "web")
        self.assertTrue(django)
        self.assertTrue(all(item.category == "web" for item in django))

        one = select_workloads(
            "realworld", "standard", "django_wsgi_request", None
        )
        self.assertEqual([item.name for item in one], ["django_wsgi_request"])
        explicit_quick = select_workloads(
            "realworld", "quick", "django_asgi_request", None
        )
        self.assertEqual([item.name for item in explicit_quick], ["django_asgi_request"])
        tooling_quick = select_workloads("realworld", "quick", None, "tooling")
        self.assertEqual(
            {item.name for item in tooling_quick},
            {"pylint_source", "compileall_source"},
        )

    def test_unknown_workload_and_profile_fail_clearly(self):
        with self.assertRaisesRegex(ValueError, "unknown workload"):
            select_workloads("realworld", "standard", "not-a-workload", None)
        with self.assertRaisesRegex(ValueError, "unknown profile"):
            select_workloads("realworld", "unrecognized", None, None)


class MemoryMetricsTests(unittest.TestCase):
    def test_smaps_rollup_converts_kib_to_bytes_and_sums_private_memory(self):
        rollup = parse_smaps_rollup(
            "00400000-00401000 r--p 00000000 00:00 0\n"
            "Rss: 3072 kB\n"
            "Pss: 2048 kB\n"
            "Private_Clean: 1000 kB\n"
            "Private_Dirty: 512 kB\n"
            "Private_Hugetlb: 4 kB\n"
            "Shared_Clean: 1200 kB\n"
            "Shared_Dirty: 300 kB\n"
            "Swap: 7 kB\n"
        )
        self.assertEqual(rollup.rss_bytes, 3072 * 1024)
        self.assertEqual(rollup.pss_bytes, 2048 * 1024)
        self.assertEqual(rollup.private_bytes, 1516 * 1024)
        self.assertEqual(rollup.swap_bytes, 7 * 1024)

    def test_missing_core_procfs_counter_is_rejected(self):
        with self.assertRaises(SmapsRollupError):
            parse_smaps_rollup(
                "Rss: 1 kB\nPss: 1 kB\nPrivate_Clean: 1 kB\nSwap: 0 kB\n"
            )

    def test_process_tree_sample_sums_each_process_once(self):
        first = SmapsRollup(
            rss_bytes=100,
            pss_bytes=70,
            private_clean_bytes=20,
            private_dirty_bytes=10,
            swap_bytes=2,
        )
        child = SmapsRollup(
            rss_bytes=80,
            pss_bytes=50,
            private_clean_bytes=15,
            private_dirty_bytes=5,
            swap_bytes=1,
        )
        sample = sum_rollups({101: first, 102: child}, elapsed_seconds=0.25)
        self.assertEqual(sample.process_count, 2)
        self.assertEqual(sample.rss_bytes, 180)
        self.assertEqual(sample.pss_bytes, 120)
        self.assertEqual(sample.private_bytes, 50)
        self.assertEqual(sample.swap_bytes, 3)
        self.assertEqual(sample.pids, (101, 102))


class ResultSchemaTests(unittest.TestCase):
    def test_common_result_round_trips_with_separate_measurement_passes(self):
        result = {
            "schema_version": 1,
            "identity": {
                "name": "django_wsgi_request",
                "category": "web",
                "operation": "request",
                "operation_count": 30,
            },
            "baseline": {
                "timing": {"samples": [0.010, 0.011]},
                "memory": {"rounds": [{"peak_pss": 1_000_000}]},
                "allocations": {
                    "rounds": [{"bytes_per_operation": 1234}],
                    "status": "complete",
                },
            },
            "candidate": {
                "timing": {"samples": [0.009, 0.010]},
                "memory": {"rounds": [{"peak_pss": 990_000}]},
                "allocations": {
                    "rounds": [{"bytes_per_operation": 1200}],
                    "status": "complete",
                },
            },
        }
        encoded = result_to_json(result)
        self.assertTrue(encoded.endswith("\n"))
        self.assertEqual(result_from_json(encoded), result)

    def test_incomplete_timing_result_is_rejected(self):
        result = {
            "identity": {
                "name": "python_startup",
                "category": "startup",
                "operation": "process",
                "operation_count": 1,
            },
            "baseline": {"timing": {"samples": []}},
            "candidate": {"timing": {"samples": [0.01]}},
        }
        with self.assertRaises(ResultSchemaError):
            result_to_json(result)

    def test_nan_timing_is_rejected_instead_of_serialized_as_a_number(self):
        result = {
            "identity": {
                "name": "python_startup",
                "category": "startup",
                "operation": "process",
                "operation_count": 1,
            },
            "baseline": {"timing": {"samples": [float("nan")]}},
            "candidate": {"timing": {"samples": [0.01]}},
        }
        with self.assertRaises(ResultSchemaError):
            result_to_json(result)


class RunnerContractTests(unittest.TestCase):
    def test_timing_and_memory_rounds_are_profile_specific(self):
        self.assertEqual(set(PROFILE_ROUNDS), {"quick", "standard", "rigorous"})
        for timing_rounds, memory_rounds in PROFILE_ROUNDS.values():
            self.assertGreater(timing_rounds, 0)
            self.assertGreater(memory_rounds, 0)

    def test_startup_runs_the_supplied_interpreter_directly(self):
        command = workload_command(
            Path("/tmp/python"),
            next(w for w in WORKLOADS if w.name == "python_startup"),
            1,
        )
        self.assertEqual(command, ["/tmp/python", "-c", "pass"])

    def test_macro_commands_do_not_require_target_venv_or_pip(self):
        python = Path("/tmp/python")
        for workload in WORKLOADS:
            with self.subTest(workload=workload.name):
                command = workload_command(python, workload, workload.iterations)
                self.assertEqual(command[0], str(python))
                self.assertNotIn("venv", command)
                self.assertNotIn("pip", command[1:])
                if workload.name != "python_startup":
                    self.assertEqual(
                        command[1:3],
                        ["-m", f"benchmarks.workloads.{workload.module}"],
                    )

    def test_benchmark_dependencies_are_external_to_the_tested_interpreter(self):
        env = workload_environment(Path("/bench/site-packages"))
        paths = env["PYTHONPATH"].split(":")
        self.assertEqual(paths[0], "/bench/site-packages")
        self.assertIn(str(ROOT), paths)
        self.assertEqual(env["PYTHONHASHSEED"], "1")
        self.assertEqual(env["PYTHONNOUSERSITE"], "1")
        self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1")


class DocumentationAndCompatibilityTests(unittest.TestCase):
    def test_readme_explains_new_measurement_and_comparison_contracts(self):
        readme = (BENCH / "README.md").read_text(encoding="utf-8")
        for phrase in (
            "Three independent passes",
            "Memray",
            "peak total PSS",
            "upstream CPython",
            "Astral PBS",
            "django_wsgi_request",
            "django_asgi_request",
            "pip_install_wheelhouse",
            "provenance.json",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, readme)

    def test_old_shell_entry_point_delegates_to_the_controller(self):
        script = (BENCH / "run_benchmarks.sh").read_text(encoding="utf-8")
        self.assertIn("benchmarks/bench.py", script)
        self.assertIn("run --preset pbs", script)
        self.assertIn('exec python3', script)
        self.assertNotIn("docker build", script)
        self.assertNotIn("run_parallel.sh", script)

    def test_unremoved_utilities_are_marked_as_legacy(self):
        for name in (
            "run_single.sh",
            "run_suite.sh",
            "run_parallel.sh",
            "compare.py",
            "pool.py",
            "shard.py",
        ):
            with self.subTest(script=name):
                path = BENCH / name
                if path.exists():
                    header = path.read_text(encoding="utf-8")[:240]
                    self.assertIn("LEGACY", header)

    def test_benchmark_image_does_not_bake_in_pbs_or_legacy_runners(self):
        dockerfile = (BENCH / "Dockerfile").read_text(encoding="utf-8")
        for baked_input in (
            "ARG PBS_URL=",
            "reference-pbs",
            "/bench/pbs/python",
            "run_single.sh",
            "run_suite.sh",
            "run_parallel.sh",
            "compare.py",
            "pool.py",
            "shard.py",
        ):
            with self.subTest(baked_input=baked_input):
                self.assertNotIn(baked_input, dockerfile)


class ControllerCliTests(unittest.TestCase):
    def test_executable_mount_preserves_non_bin_layout(self):
        with tempfile.TemporaryDirectory() as temporary:
            prefix = Path(temporary)
            executable = prefix / "custom" / "cpython"
            executable.parent.mkdir()
            executable.write_bytes(b"python")
            mounts: list[str] = []
            descriptor = _docker_descriptor(str(executable), "baseline", mounts)
            self.assertEqual(descriptor, "/interpreters/baseline/custom/cpython")
            self.assertEqual(mounts, ["-v", f"{prefix.resolve()}:/interpreters/baseline:ro"])

    def help_text(self, command: str) -> str:
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit) as exit_info:
            bench_main([command, "--help"])
        self.assertEqual(exit_info.exception.code, 0)
        return output.getvalue()

    def test_run_accepts_generic_interpreters_and_named_presets(self):
        help_text = self.help_text("run")
        for option in (
            "--baseline",
            "--candidate",
            "--baseline-label",
            "--candidate-label",
            "--preset",
            "--suite",
            "--profile",
            "--memory-interval-ms",
            "--allow-cross-version",
            "--container",
            "--local",
            "--timing-only",
        ):
            with self.subTest(option=option):
                self.assertIn(option, help_text)
        self.assertIn("pbs", help_text)

    def test_self_comparison_has_a_direct_python_input(self):
        help_text = self.help_text("self-compare")
        self.assertIn("--python", help_text)
        self.assertIn("--suite", help_text)
        self.assertIn("--profile", help_text)


if __name__ == "__main__":
    unittest.main()
