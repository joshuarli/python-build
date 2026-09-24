from __future__ import annotations

import unittest

from buildsys.standalone_compat import _compatibility_status


class CompatibilityStatusTests(unittest.TestCase):
    def test_false_probe_result_is_a_failure(self) -> None:
        self.assertEqual(_compatibility_status({"ok": False}), "failed")

    def test_explicit_failure_status_is_preserved(self) -> None:
        self.assertEqual(_compatibility_status({"status": "failed"}), "failed")

    def test_successful_probe_result_passes(self) -> None:
        self.assertEqual(_compatibility_status({"ok": True}), "passed")


if __name__ == "__main__":
    unittest.main()
