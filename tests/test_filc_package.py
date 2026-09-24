"""The Fil-C package gates reject ordinary ELF linkage and absolute runtime paths."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("filc_package_test_subject", ROOT / "build/package.py")
assert SPEC is not None and SPEC.loader is not None
PACKAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGE)


@unittest.skipUnless(
    all(shutil.which(name) for name in ("cc", "readelf", "patchelf")),
    "Fil-C ELF checks need the Linux build tools",
)
class FilCPackageIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        source = self.root / "ordinary.c"
        source.write_text("int answer(void) { return 42; }\n")
        self.ordinary = self.root / "ordinary.so"
        subprocess.run(
            ["cc", "-shared", "-fPIC", str(source), "-o", str(self.ordinary)],
            check=True, capture_output=True, text=True,
        )

    def test_foreign_runtime_dependency_is_rejected(self) -> None:
        subprocess.run(
            ["patchelf", "--add-needed", "libhost-ordinary.so", str(self.ordinary)],
            check=True, capture_output=True, text=True,
        )
        report = PACKAGE.filc_elf_evidence(self.root)
        self.assertFalse(report["ok"])
        self.assertEqual(
            report["forbidden_needed"],
            [{"path": "ordinary.so", "needed": ["libhost-ordinary.so"]}],
        )

    def test_absolute_runtime_path_is_rejected(self) -> None:
        subprocess.run(
            ["patchelf", "--set-rpath", "/opt/fil/lib", str(self.ordinary)],
            check=True, capture_output=True, text=True,
        )
        report = PACKAGE.filc_elf_evidence(self.root)
        self.assertFalse(report["ok"])
        self.assertEqual(
            report["forbidden_rpaths"],
            [{"path": "ordinary.so", "rpaths": ["/opt/fil/lib"]}],
        )

    def test_ordinary_objects_cannot_satisfy_filc_symbol_gate(self) -> None:
        suffix = ".cpython-314-x86_64-filc-linux-musl.so"
        paths = (
            "bin/python3.14.real",
            "lib/libpython3.14.so.1.0",
            *(f"lib/python3.14/lib-dynload/{name}{suffix}"
              for name in ("_ctypes", "_ssl", "_sqlite3")),
        )
        for relative in paths:
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.ordinary, destination)
        report = PACKAGE.filc_symbol_evidence(self.root)
        self.assertFalse(report["ok"])
        self.assertTrue(all(not item["ok"] for item in report["files"].values()))


if __name__ == "__main__":
    unittest.main()
