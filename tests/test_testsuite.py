"""Classification of regression-suite failures.

The register exists so that a *new* failure cannot hide behind a known one.
These tests pin that behaviour: anything not registered must surface.
"""
from __future__ import annotations

import unittest

from buildsys.testsuite import (
    CASE_EXCLUSIONS, FILE_EXCLUSIONS, classify, report_payload,
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
        # test_mailbox failed only under parallel load; it must not be
        # recorded as an accepted exclusion, because that would hide a real
        # regression in it later.
        result = classify({"test_mailbox": self._finding(0, failures=0)})
        self.assertEqual(result["accepted_exclusions"], [])
        self.assertEqual(result["unexpected_failures"], [])

    def test_registered_case_failure_is_accepted(self) -> None:
        stem, case = CASE_EXCLUSIONS[0].test.split(":", 1)
        result = classify({stem: self._finding(1, failed_cases=[case])})
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

    def test_report_payload_fails_when_something_is_unexpected(self) -> None:
        report = {
            "tests_run": "1", "failure_count": 1, "failed_files": ["test_x"],
            "classification": {"unexpected_failures": ["test_x"]},
        }
        payload = report_payload(report)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["unexpected_failures"], ["test_x"])
        self.assertEqual(payload["accepted_exclusions"], [])
        self.assertTrue(payload["exclusions"])


if __name__ == "__main__":
    unittest.main()
