"""Focused contract tests for the deterministic Django macro workloads."""

import importlib.util
import json
import math
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path


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


@unittest.skipUnless(
    DJANGO_AVAILABLE,
    "Django is supplied externally on PYTHONPATH for workload integration tests",
)
class DjangoScenarioProcessTests(unittest.TestCase):
    def run_scenario(self, scenario: str, iterations: int) -> dict:
        environment = os.environ.copy()
        python_path = environment.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = os.pathsep.join(
            part for part in (str(ROOT), python_path) if part
        )
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


if __name__ == "__main__":
    unittest.main()
