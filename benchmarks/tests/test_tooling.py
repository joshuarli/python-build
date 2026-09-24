"""Tests for the checked-in source tooling workloads."""

from __future__ import annotations

import importlib.metadata
import json
import subprocess
import sys
import unittest
from pathlib import Path

from benchmarks.workloads import tooling


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "benchmarks" / "workloads" / "fixtures" / "tooling"


def has_distribution(name: str, version: str) -> bool:
    """Return whether the exact locked tool version is importable here."""
    try:
        return importlib.metadata.version(name) == version
    except importlib.metadata.PackageNotFoundError:
        return False


class ToolingFixtureTests(unittest.TestCase):
    def test_python_corpus_is_checked_in_and_package_sized(self):
        sources = sorted((FIXTURES / "python_corpus").rglob("*.py"))
        self.assertGreaterEqual(len(sources), 20)
        self.assertGreaterEqual(sum(path.stat().st_size for path in sources), 30_000)
        self.assertFalse(any((FIXTURES / "python_corpus").rglob("__pycache__")))

    def test_c_corpus_contains_several_preprocessed_translation_units(self):
        sources = sorted((FIXTURES / "c_corpus").glob("*.i"))
        self.assertGreaterEqual(len(sources), 3)
        for source in sources:
            with self.subTest(source=source.name):
                payload = source.read_bytes()
                self.assertGreaterEqual(len(payload), 100_000)
                self.assertNotIn(b"#include", payload)
                self.assertNotIn(b"#define", payload)

    def test_fixture_manifest_explains_provenance_and_mutability(self):
        readme = (FIXTURES / "README.md").read_text()
        self.assertIn("checked-in", readme)
        self.assertIn("Do not replace them with the live", readme)


class CompileallWorkloadTests(unittest.TestCase):
    def test_compileall_emits_every_source_to_a_fresh_prefix(self):
        result = tooling.compileall_source(iterations=2)
        source_count = len(tooling._python_sources())
        self.assertEqual(result.operation_count, source_count * 2)
        self.assertRegex(result.digest, r"^[0-9a-f]{64}$")
        self.assertGreater(result.elapsed_seconds, 0.0)
        self.assertFalse(any(tooling.PYTHON_CORPUS.rglob("__pycache__")))

    def test_compileall_digest_covers_fixture_and_not_destination_path(self):
        first = tooling.compileall_source(iterations=1)
        second = tooling.compileall_source(iterations=1)
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(first.operation_count, second.operation_count)

    def test_cli_writes_one_machine_readable_result_line(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "benchmarks.workloads.tooling",
                "compileall_source",
                "--iterations",
                "2",
            ],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        lines = completed.stdout.splitlines()
        self.assertEqual(len(lines), 1)
        document = json.loads(lines[-1])
        self.assertEqual(
            set(document), {"operation_count", "digest", "elapsed_seconds"}
        )
        self.assertGreater(document["operation_count"], 0)
        self.assertRegex(document["digest"], r"^[0-9a-f]{64}$")
        self.assertGreater(document["elapsed_seconds"], 0.0)

    def test_cli_rejects_nonpositive_iterations(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "benchmarks.workloads.tooling",
                "compileall_source",
                "--iterations",
                "0",
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("iterations must be positive", completed.stderr)


@unittest.skipUnless(has_distribution("pycparser", tooling.PYCPARSER_VERSION), "locked pycparser is not installed")
class PycparserWorkloadTests(unittest.TestCase):
    def test_ast_count_and_digest_are_stable_across_passes(self):
        result = tooling.pycparser_source(iterations=2)
        self.assertGreaterEqual(result.operation_count, 20_000)
        self.assertRegex(result.digest, r"^[0-9a-f]{64}$")
        self.assertGreater(result.elapsed_seconds, 0.0)


@unittest.skipUnless(has_distribution("pylint", tooling.PYLINT_VERSION), "locked pylint is not installed")
class PylintWorkloadTests(unittest.TestCase):
    def test_diagnostic_digest_and_corpus_count_are_stable_across_passes(self):
        result = tooling.pylint_source(iterations=2)
        self.assertEqual(result.operation_count, len(tooling._python_sources()) * 2)
        self.assertRegex(result.digest, r"^[0-9a-f]{64}$")
        self.assertGreater(result.elapsed_seconds, 0.0)
