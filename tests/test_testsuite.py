"""Classification of regression-suite failures.

The register exists so that a *new* failure cannot hide behind a known one.
These tests pin that behaviour: anything not registered must surface.
"""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from buildsys.testsuite import (
    CASE_EXCLUSIONS, FILE_EXCLUSIONS, SuiteError, classify, report_payload,
    run_suite, verify_excluded_failures,
)


class ExclusionRegisterTests(unittest.TestCase):
    def test_every_exclusion_states_a_reason_and_a_consequence(self) -> None:
        for exclusion in (*FILE_EXCLUSIONS, *CASE_EXCLUSIONS):
            self.assertTrue(exclusion.reason.strip(), exclusion.test)
            self.assertTrue(exclusion.consequence.strip(), exclusion.test)

    def test_the_packaging_exclusions_are_registered(self) -> None:
        names = {e.test for e in FILE_EXCLUSIONS}
        self.assertIn("test_venv", names)
        self.assertIn("test_ensurepip", names)


class ClassifyTests(unittest.TestCase):
    def _finding(
        self,
        returncode: int,
        failures: int = 1,
        failed_cases: list[str] | None = None,
    ) -> dict:
        return {
            "returncode": returncode,
            "failures": failures,
            "failed_cases": failed_cases or [],
            "output_tail": "",
        }

    def test_registered_file_failure_is_accepted(self) -> None:
        result = classify({"test_venv": self._finding(1)})
        self.assertIn("test_venv", result["accepted_exclusions"])
        self.assertEqual(result["unexpected_failures"], [])

    def test_unregistered_failure_is_reported(self) -> None:
        result = classify({"test_newthing": self._finding(1)})
        self.assertEqual(result["unexpected_failures"], ["test_newthing"])

    def test_a_flake_that_passes_alone_is_not_an_exclusion(self) -> None:
        result = classify({"test_mailbox": self._finding(0, failures=0)})
        self.assertEqual(result["accepted_exclusions"], [])
        self.assertEqual(result["unexpected_failures"], ["test_mailbox"])

    def test_registered_case_failure_is_accepted(self) -> None:
        stem, case = CASE_EXCLUSIONS[0].test.split(":", 1)
        finding = self._finding(2, failed_cases=[case])
        finding["attempts"] = [{"complete": True}]
        result = classify({stem: finding})
        self.assertIn(stem, result["accepted_exclusions"])
        self.assertEqual(result["unexpected_failures"], [])

    def test_unregistered_case_in_registered_file_is_unexpected(self) -> None:
        stem = CASE_EXCLUSIONS[0].test.split(":", 1)[0]
        result = classify({stem: self._finding(1, failed_cases=["test_other_case"])})
        self.assertEqual(result["accepted_exclusions"], [])
        self.assertEqual(result["unexpected_failures"], [stem])

    def test_case_failure_without_parsed_method_is_unexpected(self) -> None:
        stem = CASE_EXCLUSIONS[0].test.split(":", 1)[0]
        result = classify({stem: self._finding(1)})
        self.assertEqual(result["accepted_exclusions"], [])
        self.assertEqual(result["unexpected_failures"], [stem])

    def test_registered_case_failure_with_incomplete_retry_is_unexpected(self) -> None:
        stem, case = CASE_EXCLUSIONS[0].test.split(":", 1)
        finding = self._finding(2, failed_cases=[case])
        finding["attempts"] = [{"complete": False}]
        result = classify({stem: finding})
        self.assertEqual(result["accepted_exclusions"], [])
        self.assertEqual(result["unexpected_failures"], [stem])

    def test_report_payload_fails_when_something_is_unexpected(self) -> None:
        report = {
            "tests_run": "1", "failure_count": 1, "failed_files": ["test_x"],
            "returncode": 2,
            "complete": True,
            "classification": {
                "accepted_exclusions": [],
                "unexpected_failures": ["test_x"],
            },
        }
        payload = report_payload(report)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["unexpected_failures"], ["test_x"])
        self.assertEqual(payload["accepted_exclusions"], [])
        self.assertTrue(payload["exclusions"])

    def test_report_payload_requires_classification(self) -> None:
        report = {
            "tests_run": "5",
            "failure_count": 0,
            "failed_files": [],
            "returncode": 0,
            "complete": True,
        }
        self.assertFalse(report_payload(report)["ok"])

    @patch("buildsys.testsuite.run_product_process")
    def test_retries_are_bounded_and_passing_retries_preserve_initial_failure(
        self,
        run,
    ) -> None:
        output = """== Tests result: SUCCESS ==
5 tests OK.
Total tests: run=87
Total test files: run=1/1
"""
        run.return_value = subprocess.CompletedProcess([], 0, output, "")
        finding = verify_excluded_failures(
            Path("python3.15"), ["test_mailbox"], attempts=99
        )["test_mailbox"]
        self.assertTrue(finding["initial_suite_failure"])
        self.assertEqual(finding["attempt_count"], 3)
        self.assertEqual(len(finding["attempts"]), 3)
        self.assertEqual(classify({"test_mailbox": finding})["unexpected_failures"], ["test_mailbox"])
        self.assertEqual(run.call_count, 3)


class RunSuiteTests(unittest.TestCase):
    def _completed(self, returncode: int, output: str) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess([], returncode, output, "")

    @patch("buildsys.testsuite.run_product_process")
    def test_success_summary_without_failures_field_is_complete(self, run) -> None:
        run.return_value = self._completed(
            0,
            """== Tests result: SUCCESS ==

5 tests OK.
Total tests: run=87
Total test files: run=3/3
Result: SUCCESS
""",
        )
        report = run_suite(Path("python3.15"))
        self.assertTrue(report["complete"])
        self.assertEqual(report["returncode"], 0)
        self.assertEqual(report["tests_run"], "87")
        self.assertEqual(report["failure_count"], 0)
        self.assertEqual(report["failed_files"], [])
        self.assertEqual(report["test_files_run"], report["test_files_expected"])

    @patch("buildsys.testsuite.run_product_process")
    def test_singular_failed_file_is_parsed(self, run) -> None:
        run.return_value = self._completed(
            2,
            """== Tests result: FAILURE ==

1 test failed:
    test_example

Total tests: run=87 failures=1
Total test files: run=3/3 failed=1
Result: FAILURE
""",
        )
        report = run_suite(Path("python3.15"))
        self.assertTrue(report["complete"])
        self.assertEqual(report["returncode"], 2)
        self.assertEqual(report["failure_count"], 1)
        self.assertEqual(report["failed_files"], ["test_example"])

    @patch("buildsys.testsuite.run_product_process")
    def test_abnormal_process_termination_fails_even_with_success_output(self, run) -> None:
        run.return_value = self._completed(
            -9,
            """== Tests result: SUCCESS ==
1 test OK.
Total tests: run=5
Total test files: run=1/1
""",
        )
        with self.assertRaisesRegex(SuiteError, "abnormally with status -9"):
            run_suite(Path("python3.15"))

    @patch("buildsys.testsuite.run_product_process")
    def test_zero_executed_tests_fail(self, run) -> None:
        run.return_value = self._completed(
            4,
            """== Tests result: NO TESTS RAN ==
Total tests: run=0
Total test files: run=0/3
Result: NO TESTS RAN
""",
        )
        with self.assertRaisesRegex(SuiteError, "accounting is incomplete"):
            run_suite(Path("python3.15"))

    @patch("buildsys.testsuite.run_product_process")
    def test_timed_out_test_fails_even_with_failure_summary(self, run) -> None:
        run.return_value = self._completed(
            2,
            """== Tests result: FAILURE ==
test_example timed out (600 sec)
1 test failed:
    test_example
Total tests: run=87 failures=1
Total test files: run=1/1 failed=1
""",
        )
        with self.assertRaisesRegex(SuiteError, "timed-out test"):
            run_suite(Path("python3.15"))


if __name__ == "__main__":
    unittest.main()
