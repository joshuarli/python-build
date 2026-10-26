from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from buildsys.product import PRODUCT
from buildsys.targets import TARGETS

REPO = Path(__file__).resolve().parents[1]
SCRATCH = REPO / ".work" / "tmp"
SCRATCH.mkdir(parents=True, exist_ok=True)
SPEC = importlib.util.spec_from_file_location(
    "linux_package_driver", REPO / "build" / "package.py"
)
DRIVER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = DRIVER
SPEC.loader.exec_module(DRIVER)


class LinuxPackageHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(dir=SCRATCH)
        self.addCleanup(self.temporary.cleanup)
        self.install = Path(self.temporary.name)
        self.interpreter = PRODUCT.interpreter(self.install)
        self.interpreter.parent.mkdir(parents=True)
        self.interpreter.write_bytes(b"interpreter")
        self.libpython = self.install / "lib" / "libpython3.15.so"
        self.libpython.parent.mkdir()
        self.libpython.write_bytes(b"libpython")
        self.static_executable = self.install / "bin" / "static-tool"
        self.static_executable.parent.mkdir(exist_ok=True)
        self.static_executable.write_bytes(b"static executable")
        self.static_executable.chmod(0o755)
        self.extra_elfs = []
        self.header_type = "DYN"
        self.dynamic = (
            " 0x0000000000000001 (NEEDED) Shared library: "
            "[libc.musl-x86_64.so.1]\n"
            " 0x0000000000000018 (BIND_NOW) 0x0\n"
        )
        self.program_headers = (
            "  INTERP 0x0 0x1000 0x1000 0x20 0x20 R 0x1\n"
            "  LOAD 0x0 0x1000 0x1000 0x100 0x100 R E 0x1000\n"
            "  LOAD 0x1000 0x3000 0x3000 0x100 0x100 RW 0x1000\n"
            "  GNU_STACK 0x0 0x0 0x0 0x0 0x0 RW 0x10\n"
            "  GNU_RELRO 0x1000 0x3000 0x3000 0x100 0x100 R 0x1\n"
            "  [Requesting program interpreter: /lib/ld-musl-x86_64.so.1]\n"
        )

    def _readelf(self, command: list[str], **kwargs) -> subprocess.CompletedProcess:
        if command[1] == "-hW":
            elf_type = (
                "EXEC"
                if command[-1] == str(self.static_executable)
                else self.header_type
            )
            output = (
                f"  Class: ELF64\n  Type: {elf_type}\n"
                "  Machine: Advanced Micro Devices X86-64\n"
            )
        elif command[1] == "-dW":
            output = (
                "There is no dynamic section in this file.\n"
                if command[-1] == str(self.static_executable)
                else self.dynamic
            )
        elif command[1] == "-lW":
            output = self.program_headers
            if command[-1] != str(self.interpreter):
                output = "\n".join(
                    line for line in output.splitlines()
                    if not line.lstrip().startswith("INTERP")
                    and "Requesting program interpreter" not in line
                )
        elif command[1] == "--dyn-syms":
            output = "__stack_chk_fail\n" if command[-1] == str(self.libpython) else ""
        else:
            raise AssertionError(command)
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")

    def _product_process(self, command: list[str], *args, **kwargs):
        code = command[-1]
        if "INSTSONAME" in code:
            output = "libpython3.15.so\n"
        elif "CFLAGS" in code:
            output = json.dumps({
                "CFLAGS": "-O3 -fstack-protector-strong -D_FORTIFY_SOURCE=2",
                "CFLAGS_NODIST": "",
                "PY_CFLAGS": "",
                "PY_CFLAGS_NODIST": "",
                "CPPFLAGS": "",
            })
        else:
            output = ""
        return SimpleNamespace(returncode=0, stdout=output, stderr="")

    def _validate(self) -> dict:
        with (
            patch.object(DRIVER, "TARGET_DESCRIPTION", TARGETS["x86_64-unknown-linux-musl"]),
            patch.object(
                DRIVER,
                "find_elfs",
                return_value=[self.interpreter, self.libpython, *self.extra_elfs],
            ),
            patch.object(DRIVER, "_run", side_effect=self._readelf),
            patch.object(DRIVER, "run_product_process", side_effect=self._product_process),
        ):
            return DRIVER._linux_validation(self.install)

    def test_final_elf_images_pass_pie_relro_and_relocation_gates(self) -> None:
        report = self._validate()

        self.assertTrue(report["ok"], report["failed"])
        self.assertTrue(report["checks"]["elf_pie"]["ok"])
        self.assertTrue(report["checks"]["elf_relro"]["ok"])
        self.assertTrue(report["checks"]["elf_writable_executable"]["ok"])
        self.assertTrue(report["checks"]["elf_text_relocations"]["ok"])

    def test_static_et_exec_is_included_in_pie_gate(self) -> None:
        self.extra_elfs.append(self.static_executable)

        report = self._validate()

        self.assertFalse(report["checks"]["elf_pie"]["ok"])
        self.assertIn(
            str(self.static_executable.relative_to(self.install)),
            report["checks"]["elf_pie"]["violations"],
        )

    def test_final_elf_images_fail_when_hardening_evidence_is_missing(self) -> None:
        self.header_type = "EXEC"
        self.dynamic = (
            " 0x0000000000000001 (NEEDED) Shared library: "
            "[libc.musl-x86_64.so.1]\n"
            " 0x0000000000000016 (TEXTREL) 0x0\n"
        )
        self.program_headers = (
            "  INTERP 0x0 0x1000 0x1000 0x20 0x20 R 0x1\n"
            "  LOAD 0x0 0x1000 0x1000 0x100 0x100 RWE 0x1000\n"
            "  GNU_STACK 0x0 0x0 0x0 0x0 0x0 RW 0x10\n"
        )

        report = self._validate()
        checks = report["checks"]

        self.assertFalse(report["ok"])
        self.assertFalse(checks["elf_pie"]["ok"])
        self.assertFalse(checks["elf_relro"]["ok"])
        self.assertFalse(checks["elf_writable_executable"]["ok"])
        self.assertFalse(checks["elf_text_relocations"]["ok"])


if __name__ == "__main__":
    unittest.main()
