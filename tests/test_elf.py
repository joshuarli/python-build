from __future__ import annotations

import unittest

from buildsys.elf import (
    dynamic_tags,
    gnu_stack_report,
    hardening_report,
    linkage_report,
    machine_report,
)
from buildsys.product import PRODUCT
from pathlib import Path
import tempfile


class LinkageReportTests(unittest.TestCase):
    def test_parses_dynamic_dependencies_and_relative_search_paths(self) -> None:
        dynamic = (
            " 0x0000000000000001 (NEEDED) Shared library: [libpython3.15.so.1.0]\n"
            " 0x000000000000001d (RUNPATH) Library runpath: [$ORIGIN/../lib]\n"
        )
        self.assertEqual(dynamic_tags(dynamic), {
            "needed": ["libpython3.15.so.1.0"],
            "rpath": [],
            "runpath": ["$ORIGIN/../lib"],
        })

    def test_resolves_package_libraries_and_rejects_unsafe_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "bin").mkdir()
            (root / "lib").mkdir()
            (root / "lib" / "libpython3.15.so.1.0").write_bytes(b"libpython")
            report = linkage_report(
                root,
                root / "bin" / PRODUCT.interpreter_name,
                needed=["libpython3.15.so.1.0", "libc.musl-x86_64.so.1"],
                runpaths=["$ORIGIN/../lib"],
                system_libraries={"libc.musl-x86_64.so.1"},
            )
            unsafe = linkage_report(
                root,
                root / "bin" / PRODUCT.interpreter_name,
                needed=["libpython3.15.so.1.0"],
                runpaths=["/opt/homebrew/lib"],
                system_libraries=set(),
            )
        self.assertTrue(report["ok"])
        self.assertFalse(unsafe["ok"])
        self.assertIn("unsafe runpath", unsafe["runpath_violations"][0])

    def test_rejects_missing_libraries_and_root_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "bin").mkdir()
            report = linkage_report(
                root,
                root / "bin" / PRODUCT.interpreter_name,
                needed=["libmissing.so"],
                runpaths=["$ORIGIN/../../outside"],
                system_libraries=set(),
            )
        self.assertFalse(report["ok"])
        self.assertEqual(report["missing_product_libraries"], ["libmissing.so"])
        self.assertTrue(report["runpath_violations"])

    def test_machine_report_requires_64_bit_expected_architecture(self) -> None:
        output = "  Class: ELF64\n  Machine: AArch64\n"
        self.assertTrue(machine_report(output, "aarch64")["ok"])
        self.assertFalse(machine_report(output, "x86_64")["ok"])


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
                PRODUCT.interpreter_name: "",
                "libpython": "  4: 0000000000000000 0 FUNC GLOBAL DEFAULT UND __stack_chk_fail\n",
            },
        )

        self.assertTrue(report["ok"])
        self.assertFalse(
            report["stack_protector_dynamic_references"][PRODUCT.interpreter_name]
        )
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
