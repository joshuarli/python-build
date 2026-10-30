from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from buildsys.package import create_archive
from buildsys.reproduce import compare_archives


def archive(root: Path, name: str, files: dict[str, bytes]) -> Path:
    install = root / f"install-{name}"
    for relative, content in files.items():
        path = install / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    path = root / f"{name}.tar.gz"
    create_archive(install, path)
    return path


class CompareArchivesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def compare(self, first: dict[str, bytes], second: dict[str, bytes]) -> dict:
        return compare_archives(
            archive(self.root, "a", first), archive(self.root, "b", second), self.root / "scratch"
        )

    def test_identical_builds_are_reproducible(self) -> None:
        files = {"bin/python": b"\x7fELF binary", "lib/data.txt": b"text"}
        report = self.compare(files, files)
        self.assertTrue(report["reproducible"], report)
        self.assertTrue(report["raw_archives_identical"])

    def test_a_differing_non_macho_file_is_a_finding(self) -> None:
        report = self.compare(
            {"lib/sysconfig.py": b"BINDIR='/build-a/bin'"},
            {"lib/sysconfig.py": b"BINDIR='/build-b/bin'"},
        )
        self.assertFalse(report["reproducible"])
        self.assertEqual(len(report["content_differences"]), 1)

    def test_missing_files_are_structural_differences(self) -> None:
        report = self.compare({"a": b"1", "b": b"2"}, {"a": b"1"})
        self.assertFalse(report["reproducible"])
        self.assertTrue(report["structural_differences"]["only_in_first"])


if __name__ == "__main__":
    unittest.main()
