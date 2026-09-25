"""Patch discipline: provenance, applicability, and effect."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from buildsys.patches import PatchError, apply_patch, apply_patch_set

REPO = Path(__file__).resolve().parent.parent
PATCH_DIR = REPO / "patches" / "cpython"
CPYTHON_SOURCE = REPO / "src" / "Python-3.14.6"


class PatchProvenanceTests(unittest.TestCase):
    def test_every_patch_has_a_provenance_note(self) -> None:
        for patch in PATCH_DIR.glob("*.patch"):
            note = patch.with_suffix(".md")
            self.assertTrue(note.is_file(), f"{patch.name} is missing its provenance note")
            text = note.read_text()
            for required in ("Upstream source", "Explanation", "Scope", "Applicability check", "Regression test"):
                self.assertIn(required, text, f"{note.name} missing '{required}' section")


class ApplyPatchTests(unittest.TestCase):
    def test_unknown_patch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(PatchError):
                apply_patch(Path(tmp), PATCH_DIR / "does-not-exist.patch")

    def test_mismatched_source_is_rejected_not_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            (source / "Misc").mkdir()
            (source / "Misc" / "python-config.sh.in").write_text("already different content\n")
            with self.assertRaises(PatchError):
                apply_patch_set(source, PATCH_DIR)


@unittest.skipUnless(CPYTHON_SOURCE.is_dir(), "verified CPython source not extracted locally")
class PythonConfigQuotingTests(unittest.TestCase):
    def test_patch_removes_the_unquoted_cd_substitution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "Python-3.14.6"
            shutil.copytree(CPYTHON_SOURCE / "Misc", source / "Misc")
            target = source / "Misc" / "python-config.sh.in"
            before = target.read_text()
            self.assertIn('RESULT=$(dirname $(cd $(dirname "$1") && pwd -P))', before)

            apply_patch_set(source, PATCH_DIR)

            after = target.read_text()
            self.assertNotIn('RESULT=$(dirname $(cd $(dirname "$1") && pwd -P))', after)
            self.assertIn('RESULT=$(dirname "$(cd "$(dirname "$1")" && pwd -P)")', after)


if __name__ == "__main__":
    unittest.main()
