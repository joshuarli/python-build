"""Stable complete-patch identities for the public difflib workloads."""

from __future__ import annotations

import unittest

from benchmarks.workloads import difflib


class DifflibWorkloadTests(unittest.TestCase):
    def test_complete_unified_diffs_have_fixed_inputs_and_output(self) -> None:
        cases = {
            "difflib_unified_mostly_equal": (
                "25b83537c564e95a74f38ae2a79a710f92c832660a7c7e9f660b4a3dee2fe842",
                "b5e86d88c7cad40f06a1ca79c7c2869a223315fdb30bdc7cd8940849414af2a3",
            ),
            "difflib_unified_reordered": (
                "4534585365055d7f64ab4c2582f9dd14ae83bdd90055f920bdb7a35a7f0e20f3",
                "26585b44b4a4ced0dbb5f717454d1cbc7fd290ad798a767f0de0ecd41497f7c8",
            ),
        }
        for name, (input_digest, output_digest) in cases.items():
            with self.subTest(name=name):
                result = getattr(difflib, name)(2)
                self.assertEqual(result["operation_count"], 2)
                self.assertEqual(result["input_digest"], input_digest)
                self.assertEqual(result["digest"], output_digest)
                self.assertGreater(result["elapsed_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
