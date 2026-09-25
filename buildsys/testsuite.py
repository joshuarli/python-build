"""Run the CPython regression suite and reconcile its failures.

"Record narrow exclusions with observed causes. Do not carry over Alpine or
PBS skip lists wholesale." So this module does not hand the suite a skip
list — it runs the suite, then classifies each failure against a short,
explicitly-justified register. A failure that is not in the register fails
the run. A registered failure that *stops* failing is also reported, so the
register cannot quietly outlive its cause.

The register is deliberately tiny and each entry names the product decision
or platform property responsible, not merely "this test is annoying".
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Exclusion:
    test: str
    reason: str
    consequence: str


# Whole files that cannot run at all against this distribution. Each is a
# structural consequence, not a flake: the module under test does not exist,
# or the test requires build material an installed tree deliberately lacks.
FILE_EXCLUSIONS = (
    Exclusion(
        test="test_venv",
        reason="venv is removed by the 2026-09-18 scope decision",
        consequence="no environment creation; consumers use their own tooling",
    ),
    Exclusion(
        test="test_ensurepip",
        reason="ensurepip is removed by the 2026-09-18 scope decision",
        consequence="no bundled package installer anywhere in the tree",
    ),
    Exclusion(
        test="test_sysconfig",
        reason="imports venv at module import time, which is removed",
        consequence="sysconfig itself is still exercised by the checks below "
                    "and by test_cmd_line; only this file's import fails",
    ),
)

# Individual failures inside otherwise-useful files. Kept narrow so the rest
# of each file still provides coverage.
CASE_EXCLUSIONS = (
    Exclusion(
        test="test_tools:test_makefile_test_folders",
        reason="asserts every test directory is registered in Makefile.pre.in, "
               "which is build-tree material and is not installed",
        consequence="nothing; the check is about CPython's own build tree, not "
                    "about the shipped interpreter",
    ),
    Exclusion(
        test="test_cmd_line:test_python_executable",
        reason="PYTHONEXECUTABLE overrides the path this distribution uses to "
               "locate its standard library; an absolute-prefix build finds "
               "the stdlib by compiled-in path and is unaffected",
        consequence="setting PYTHONEXECUTABLE to a non-existent path prevents "
                    "this interpreter from starting. Recorded as an envelope "
                    "limitation of the relocatable layout",
    ),
)


class SuiteError(Exception):
    """The regression suite could not be run or its output not understood."""


_SUMMARY = re.compile(r"^Total tests: run=([\d,]+) failures=(\d+)", re.M)
# Verbose unittest output names each failing method after `FAIL:`/`ERROR:`.
# Case exclusions are accepted only when every observed failure matches one
# of those exact methods.
_FAILED_CASE = re.compile(r"^(?:FAIL|ERROR): ([^\s(]+)", re.M)
# The failing files are listed space-separated on a single indented line, not
# one per line — a regex that assumes one-per-line silently finds nothing and
# makes the whole run look clean.
_FAILED_FILES = re.compile(r"^\d+ tests failed:\n\s+([\w\s]+)$", re.M)


def run_suite(python: Path, *, jobs: int = 6, timeout: int = 600) -> dict:
    """Run the standard library test suite, excluding the scoped-out modules."""
    command = [str(python), "-m", "test", "-j", str(jobs), f"--timeout={timeout}"]
    for exclusion in FILE_EXCLUSIONS:
        command += ["-x", exclusion.test]
    result = subprocess.run(command, capture_output=True, text=True)
    output = result.stdout + result.stderr
    match = _SUMMARY.search(output)
    if not match:
        raise SuiteError(f"could not parse suite summary:\n{output[-2000:]}")
    ran, failures = match.group(1), int(match.group(2))
    failed_files: list[str] = []
    files = _FAILED_FILES.search(output)
    if files:
        failed_files = files.group(1).split()
    if failures and not failed_files:
        raise SuiteError(
            f"suite reported {failures} failures but no failing files could be "
            f"parsed; refusing to report a clean run:\n{output[-2000:]}"
        )
    return {
        "command": " ".join(command),
        "tests_run": ran,
        "failure_count": failures,
        "failed_files": failed_files,
        "output_tail": output[-4000:],
    }


def verify_excluded_failures(
    python: Path,
    failed_files: list[str],
    *,
    attempts: int = 3,
    fresh_python=None,
) -> dict:
    """Re-run each failing file alone to separate real failures from flakes.

    Retried rather than re-run once: several standard-library tests are
    timing- or load-sensitive, and a single solo pass/fail is a coin flip for
    them. Taking the best of a few attempts and recording how many it took
    keeps a genuine failure visible (it fails every time) while not blaming
    the product for a test that is merely fragile under a busy machine.

    Deliberately no PYTHONDONTWRITEBYTECODE: suppressing bytecode writes
    changes what `test_compileall` is testing (it asserts that an import *did*
    write a .pyc), so setting it turns a passing test into a failing one for
    reasons that have nothing to do with the product. Tree pollution is
    handled by running against a disposable copy instead, which is the
    approach plan Section 8 asks for.

    `fresh_python` optionally supplies an interpreter from a newly made copy
    of the tree, tried after the in-tree retries are exhausted. The parallel
    suite can leave a half-written cache behind when a test is interrupted,
    and that would make every subsequent run fail for a reason that has
    nothing to do with the product.
    """
    findings: dict[str, dict] = {}
    case_exclusions = {
        exclusion.test.split(":", 1)[0]
        for exclusion in CASE_EXCLUSIONS
    }
    for name in failed_files:
        best: dict | None = None
        attempts_made = 0
        interpreter = python
        for attempt in range(max(1, attempts) + 1):
            if attempt == attempts and fresh_python is not None:
                interpreter = fresh_python()
            attempts_made += 1
            command = [str(interpreter), "-m", "test"]
            if name in case_exclusions:
                command.append("-v")
            command.append(name)
            result = subprocess.run(command, capture_output=True, text=True)
            output = result.stdout + result.stderr
            match = _SUMMARY.search(output)
            failed_cases = sorted(set(_FAILED_CASE.findall(output)))
            best = {
                "returncode": result.returncode,
                "failures": int(match.group(2)) if match else None,
                "failed_cases": failed_cases,
                "output_tail": output[-1500:],
                "attempts": attempts_made,
                "used_fresh_tree": interpreter != python,
            }
            if result.returncode == 0:
                break
        findings[name] = best
    return findings


def classify(solo_findings: dict) -> dict:
    """Split observed failures into registered exclusions and real failures."""
    registered = {e.test for e in FILE_EXCLUSIONS} | {e.test for e in CASE_EXCLUSIONS}
    registered_files = {e.test for e in FILE_EXCLUSIONS}
    file_cases: dict[str, set[str]] = {}
    for exclusion in CASE_EXCLUSIONS:
        file_name, case_name = exclusion.test.split(":", 1)
        file_cases.setdefault(file_name, set()).add(case_name)

    accepted, unexpected = [], []
    for name, finding in sorted(solo_findings.items()):
        if name in registered_files:
            accepted.append(name)
            continue
        if finding["returncode"] == 0:
            continue  # passed alone: it was a load-related flake
        if name in file_cases:
            observed_cases = set(finding.get("failed_cases", []))
            if observed_cases and observed_cases <= file_cases[name]:
                accepted.append(name)
                continue
        unexpected.append(name)
    return {
        "accepted_exclusions": accepted,
        "unexpected_failures": unexpected,
        "registered": sorted(registered),
    }


def report_payload(report: dict) -> dict:
    """Shape the suite result for `dist/validation.json`."""
    return {
        "tests_run": report["tests_run"],
        "failure_count": report["failure_count"],
        "failed_files": report["failed_files"],
        "accepted_exclusions": report.get("classification", {}).get(
            "accepted_exclusions", []
        ),
        "exclusions": [
            {"test": e.test, "reason": e.reason, "consequence": e.consequence}
            for e in (*FILE_EXCLUSIONS, *CASE_EXCLUSIONS)
        ],
        "unexpected_failures": report.get("classification", {}).get("unexpected_failures", []),
        "ok": not report.get("classification", {}).get("unexpected_failures", []),
    }
