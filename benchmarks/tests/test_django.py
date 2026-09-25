"""Focused contract tests for the deterministic Django macro workloads."""

import importlib.util
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
DJANGO_AVAILABLE = importlib.util.find_spec("django") is not None


class DjangoWorkloadCliTests(unittest.TestCase):
    def test_zero_iterations_is_rejected_before_importing_django(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "benchmarks.workloads.django",
                "django_wsgi_request",
                "--iterations",
                "0",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("iterations must be a positive integer", completed.stderr)

    def test_first_request_issues_one_exchange(self):
        from benchmarks.workloads import django as workload

        modules = {name: type(sys)(name) for name in (
            "django", "django.core", "django.core.handlers", "django.core.handlers.wsgi",
        )}
        modules["django.core.handlers.wsgi"].WSGIHandler = object
        with patch.dict(os.environ, {"BENCH_DJANGO_FIXTURE_PATH": "/unused/fixture"}), \
             patch.object(workload, "_setup_application"), \
             patch.object(workload, "_wsgi_exchange", return_value=(200, b"{}")) as exchange, \
             patch.object(workload, "_validate_post_response"), \
             patch.dict(sys.modules, modules):
            result = workload.run_scenario("django_wsgi_first_request", 1)
        exchange.assert_called_once()
        self.assertEqual(result.operation_count, 1)
        self.assertIsNone(result.elapsed_seconds)
        with self.assertRaises(ValueError):
            workload.run_scenario("django_wsgi_first_request", 2)


@unittest.skipUnless(
    DJANGO_AVAILABLE,
    "Django is supplied externally on PYTHONPATH for workload integration tests",
)
class DjangoScenarioProcessTests(unittest.TestCase):
    def run_scenario(self, scenario: str, iterations: int, *, fixture: Path | None = None) -> dict:
        environment = os.environ.copy()
        python_path = environment.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = os.pathsep.join(
            part for part in (str(ROOT), python_path) if part
        )
        if fixture is not None:
            environment["BENCH_DJANGO_FIXTURE_PATH"] = str(fixture)
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "benchmarks.workloads.django",
                scenario,
                "--iterations",
                str(iterations),
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        self.assertEqual(
            completed.returncode,
            0,
            f"{scenario} failed:\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )
        lines = completed.stdout.splitlines()
        self.assertTrue(lines, f"{scenario} did not print its JSON result")
        result = json.loads(lines[-1])
        self.assertEqual(
            set(result), {"operation_count", "elapsed_seconds", "digest"}
        )
        self.assertIsInstance(result["operation_count"], int)
        self.assertGreater(result["operation_count"], 0)
        if scenario == "django_wsgi_first_request":
            self.assertIsNone(result["elapsed_seconds"])
        else:
            self.assertTrue(math.isfinite(result["elapsed_seconds"]))
            self.assertGreater(result["elapsed_seconds"], 0)
        self.assertRegex(result["digest"], re.compile(r"\A[0-9a-f]{64}\Z"))
        return result

    def test_required_scenarios_report_their_operation_counts(self):
        expected_counts = {
            "django_wsgi_request": 2,
            "django_asgi_request": 2,
            "django_orm_10k": 20_000,
            "django_template_realistic": 2,
        }
        for scenario, operation_count in expected_counts.items():
            with self.subTest(scenario=scenario):
                result = self.run_scenario(scenario, iterations=2)
                self.assertEqual(result["operation_count"], operation_count)

    def test_wsgi_digest_is_stable_across_fresh_processes(self):
        first = self.run_scenario("django_wsgi_request", iterations=2)
        second = self.run_scenario("django_wsgi_request", iterations=2)
        self.assertEqual(first["digest"], second["digest"])

    def test_first_request_uses_stable_prepared_fixture(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary) / "posts.sqlite3"
            second_fixture = Path(temporary) / "posts-again.sqlite3"
            environment = os.environ.copy()
            environment["PYTHONPATH"] = os.pathsep.join(
                part for part in (str(ROOT), environment.get("PYTHONPATH", "")) if part
            )
            def prepare(path: Path) -> dict:
                completed = subprocess.run(
                    [sys.executable, "-m", "benchmarks.workloads.django", "--prepare-fixture", str(path)],
                    cwd=ROOT, env=environment, capture_output=True, text=True, check=True, timeout=120,
                )
                return json.loads(completed.stdout)

            prepared = prepare(fixture)
            fixture_digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
            self.assertEqual(prepared["fixture_sha256"], fixture_digest)
            self.assertEqual(prepare(second_fixture)["fixture_sha256"], fixture_digest)
            fixture.chmod(0o444)
            first = self.run_scenario("django_wsgi_first_request", 1, fixture=fixture)
            second = self.run_scenario("django_wsgi_first_request", 1, fixture=fixture)
            self.assertEqual(first["operation_count"], 1)
            self.assertEqual(first["digest"], second["digest"])
            self.assertEqual(first["digest"], self.run_scenario("django_wsgi_request", 1)["digest"])
            self.assertEqual(hashlib.sha256(fixture.read_bytes()).hexdigest(), fixture_digest)


if __name__ == "__main__":
    unittest.main()
