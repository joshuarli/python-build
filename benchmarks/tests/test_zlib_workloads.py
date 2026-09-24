"""Correctness identities for the public zlib benchmark workloads."""

from __future__ import annotations

import unittest

from benchmarks.workloads import zlib
from benchmarks.workloads.registry import BY_NAME


class ZlibWorkloadTests(unittest.TestCase):
    def test_public_paths_report_stable_content_and_work_units(self) -> None:
        cases = {
            "zlib_decode_1m": (2_097_152, "a316f38cceaae9765acdb3de5b4a4ca9d59be014d03d053c10002baa3dad51fb"),
            "zlib_stream_4k": (2_097_152, "a316f38cceaae9765acdb3de5b4a4ca9d59be014d03d053c10002baa3dad51fb"),
            "gzip_extract_1m": (1_048_576, "6eb307fbef685d28bb65e832fe7c3601720b61272f303e9f66f816f55ef89055"),
            "zip_read_wheel": (2_103_316, "e1b97843b19af113cbb090fc676658ff5620f4896a5c1bb8f424ff75ac186071"),
            "zipimport_cold": (1, "2a5a6664823ee7feab0154eac0c6c3cd0ed391db89896ff798678bdd7789953f"),
        }
        for name, (units, digest) in cases.items():
            with self.subTest(name=name):
                self.assertEqual(BY_NAME[name].module, "zlib")
                result = getattr(zlib, name)(1)
                self.assertEqual(result["operation_count"], units)
                self.assertEqual(result["digest"], digest)
                self.assertEqual(len(result["input_digest"]), 64)


if __name__ == "__main__":
    unittest.main()
