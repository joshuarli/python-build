from __future__ import annotations

import unittest

from buildsys.elf import gnu_stack_report, hardening_report


class GNUStackReportTests(unittest.TestCase):
    def test_reports_non_executable_stack(self) -> None:
        report = gnu_stack_report(
            "  GNU_STACK      0x000000 0x000000 0x000000 0x000000 0x000000 RW 0x10\n"
        )

        self.assertEqual(report["flags"], "RW")
        self.assertFalse(report["executable"])
        self.assertTrue(report["ok"])

    def test_executable_stack_fails(self) -> None:
        report = gnu_stack_report(
            "  GNU_STACK      0x000000 0x000000 0x000000 0x000000 0x000000 RWE 0x10\n"
        )

        self.assertTrue(report["executable"])
        self.assertFalse(report["ok"])

    def test_missing_duplicate_and_malformed_records_fail(self) -> None:
        missing = gnu_stack_report("  LOAD 0x0 0x0 0x0 0x0 0x0 R 0x1000\n")
        duplicate = gnu_stack_report(
            "  GNU_STACK 0x0 0x0 0x0 0x0 0x0 RW 0x10\n"
            "  GNU_STACK 0x0 0x0 0x0 0x0 0x0 RW 0x10\n"
        )
        malformed = gnu_stack_report(
            "  GNU_STACK 0x0 0x0 0x0 0x0 0x0 ? 0x10\n"
        )

        self.assertFalse(missing["ok"])
        self.assertFalse(duplicate["ok"])
        self.assertFalse(malformed["ok"])


class HardeningReportTests(unittest.TestCase):
    def test_accepts_musl_hardening_evidence_without_glibc_chk_symbols(self) -> None:
        report = hardening_report(
            "-O3 -fstack-protector-strong -D_FORTIFY_SOURCE=2",
            {
                "python3.14": "",
                "libpython": "  4: 0000000000000000 0 FUNC GLOBAL DEFAULT UND __stack_chk_fail\n",
            },
        )

        self.assertTrue(report["ok"])
        self.assertFalse(report["stack_protector_dynamic_references"]["python3.14"])
        self.assertTrue(report["stack_protector_dynamic_references"]["libpython"])

    def test_missing_flags_or_libpython_guard_fail(self) -> None:
        missing_fortify = hardening_report(
            "-O3 -fstack-protector-strong",
            {"libpython": "__stack_chk_fail"},
        )
        missing_guard = hardening_report(
            "-O3 -fstack-protector-strong -D_FORTIFY_SOURCE=2",
            {"libpython": ""},
        )

        self.assertFalse(missing_fortify["ok"])
        self.assertFalse(missing_guard["ok"])


if __name__ == "__main__":
    unittest.main()
