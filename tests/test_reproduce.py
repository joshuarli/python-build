"""Two-clean-build comparison logic."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from buildsys.reproduce import compare_trees


class CompareTreesTests(unittest.TestCase):
    def test_identical_trees_report_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            (a / "bin").mkdir(parents=True)
            (b / "bin").mkdir(parents=True)
            (a / "bin" / "python3.14").write_bytes(b"same content")
            (b / "bin" / "python3.14").write_bytes(b"same content")

            report = compare_trees(a, b)

            self.assertTrue(report["byte_identical"])
            self.assertEqual(report["content_differs"], [])
            self.assertEqual(report["only_in_first"], [])
            self.assertEqual(report["only_in_second"], [])

    def test_detects_content_and_path_set_differences(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            a.mkdir()
            b.mkdir()
            (a / "shared.txt").write_bytes(b"first build\n")
            (b / "shared.txt").write_bytes(b"second build\n")
            (a / "only-a.txt").write_bytes(b"x")
            (b / "only-b.txt").write_bytes(b"y")

            report = compare_trees(a, b)

            self.assertFalse(report["byte_identical"])
            self.assertEqual(report["content_differs"], ["shared.txt"])
            self.assertEqual(report["only_in_first"], ["only-a.txt"])
            self.assertEqual(report["only_in_second"], ["only-b.txt"])


if __name__ == "__main__":
    unittest.main()
