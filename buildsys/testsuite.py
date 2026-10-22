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

from .product_process import run_product_process

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


_SUMMARY = re.compile(
    r"^Total tests: run=([\d,]+)(?: \(filtered\))?"
    r"(?: failures=([\d,]+))?(?: skipped=([\d,]+))?$",
    re.M,
)
_TOTAL_FILES = re.compile(
    r"^Total test files: run=(\d+)(?:/(\d+))?( \(filtered\))?(?: .*)?$",
    re.M,
)
_RESULT_STATE = re.compile(r"^== Tests result: (.+) ==$", re.M)
_FILE_FAILURE_COUNT = re.compile(
    r"^Total test files: .*? failed=(\d+)(?: |$)", re.M
)
_FAILED_FILE_LIST = re.compile(
    r"^(\d+) tests? failed:\s*\n((?:[ \t]+\S.*(?:\n|$))+)", re.M
)
_FAILED_CASE = re.compile(r"^(?:FAIL|ERROR): ([^\s(]+)", re.M)
_TIMED_OUT_TEST = re.compile(r"\btest[\w.]* timed out \(")
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _output_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def _failed_files(output: str) -> list[str]:
    match = _FAILED_FILE_LIST.search(output)
    if not match:
        return []
    names = match.group(2).split()
    if len(names) != int(match.group(1)) or len(names) != len(set(names)):
        raise SuiteError("failed test file list did not match its count")
    return names


def _accounting(output: str) -> dict:
    output = _ANSI_ESCAPE.sub("", output)
    summary = _SUMMARY.search(output)
    total_files = _TOTAL_FILES.search(output)
    state = _RESULT_STATE.search(output)
    if not summary or not total_files or not state:
        raise SuiteError("could not parse complete suite accounting")

    tests_run = int(summary.group(1).replace(",", ""))
    failures = int((summary.group(2) or "0").replace(",", ""))
    files_run = int(total_files.group(1))
    files_expected = int(total_files.group(2) or "0")
    failed_files = _failed_files(output)
    failed_file_match = _FILE_FAILURE_COUNT.search(output)
    failed_file_count = int(failed_file_match.group(1)) if failed_file_match else 0
    result_state = state.group(1)

    if (
        tests_run <= 0
        or files_run <= 0
        or files_expected <= 0
        or files_run != files_expected
        or "(filtered)" in summary.group(0)
        or total_files.group(3)
        or failed_file_count != len(failed_files)
    ):
        raise SuiteError("suite execution accounting is incomplete or inconsistent")

    if result_state == "SUCCESS":
        if failures or failed_files:
            raise SuiteError("successful suite summary contains failures")
    elif result_state == "FAILURE":
        if not failed_files:
            raise SuiteError("failed suite summary has no failed test files")
    else:
        raise SuiteError(f"suite ended in non-success state: {result_state}")

    return {
        "tests_run": summary.group(1),
        "failure_count": failures,
        "failed_files": failed_files,
        "test_files_run": files_run,
        "test_files_expected": files_expected,
        "result_state": result_state,
    }


def run_suite(python: Path, *, jobs: int = 6, timeout: int = 600) -> dict:
    python = Path(python).resolve()
    install = python.parent.parent
    command = [str(python), "-B", "-m", "test", "-j", str(jobs), f"--timeout={timeout}"]
    for exclusion in FILE_EXCLUSIONS:
        command += ["-x", exclusion.test]
    try:
        result = run_product_process(
            command, install, install, timeout_seconds=timeout + 60
        )
    except subprocess.TimeoutExpired as error:
        output = _output_text(error.stdout) + _output_text(error.stderr)
        raise SuiteError(f"suite process timed out:\n{output[-2000:]}") from error
    except OSError as error:
        raise SuiteError(f"suite process could not start: {error}") from error
    output = _ANSI_ESCAPE.sub("", result.stdout + result.stderr)
    if _TIMED_OUT_TEST.search(output):
        raise SuiteError(f"suite reported a timed-out test:\n{output[-2000:]}")
    try:
        accounting = _accounting(output)
    except SuiteError as error:
        raise SuiteError(f"{error}:\n{output[-2000:]}") from error
    if result.returncode == 0 and accounting["result_state"] != "SUCCESS":
        raise SuiteError(
            f"suite process exited successfully with "
            f"{accounting['result_state']}:\n{output[-2000:]}"
        )
    if result.returncode == 2 and accounting["result_state"] != "FAILURE":
        raise SuiteError(
            f"suite process exited with test-failure status but reported "
            f"{accounting['result_state']}:\n{output[-2000:]}"
        )
    if result.returncode not in (0, 2):
        raise SuiteError(
            f"suite process exited abnormally with status {result.returncode}:\n"
            f"{output[-2000:]}"
        )
    return {
        "command": " ".join(command),
        **accounting,
        "returncode": result.returncode,
        "complete": True,
        "output_tail": output[-4000:],
    }


def verify_excluded_failures(
    python: Path,
    failed_files: list[str],
    *,
    attempts: int = 3,
    fresh_python=None,
) -> dict:
    """Collect bounded, visible diagnostics for files that failed the suite."""
    python = Path(python).resolve()
    findings: dict[str, dict] = {}
    case_exclusions = {
        exclusion.test.split(":", 1)[0]
        for exclusion in CASE_EXCLUSIONS
    }
    retry_count = min(max(attempts, 1), 3)
    for name in failed_files:
        attempt_results: list[dict] = []
        for attempt in range(retry_count + (fresh_python is not None)):
            interpreter = (
                fresh_python()
                if fresh_python is not None and attempt == retry_count
                else python
            )
            command = [str(interpreter), "-B", "-m", "test"]
            if name in case_exclusions:
                command.append("-v")
            command.extend(("--timeout=600", name))
            try:
                interpreter = Path(interpreter).resolve()
                result = run_product_process(
                    command,
                    interpreter.parent.parent,
                    interpreter.parent.parent,
                    timeout_seconds=600,
                )
                output = _ANSI_ESCAPE.sub("", result.stdout + result.stderr)
                accounting_error = None
                if _TIMED_OUT_TEST.search(output):
                    accounting = None
                    accounting_error = "suite reported a timed-out test"
                else:
                    try:
                        accounting = _accounting(output)
                    except SuiteError as error:
                        accounting = None
                        accounting_error = str(error)
                diagnostic_complete = bool(
                    accounting
                    and (
                        result.returncode == 0
                        and accounting["result_state"] == "SUCCESS"
                        or result.returncode == 2
                        and accounting["result_state"] == "FAILURE"
                    )
                )
                attempt_results.append({
                    "returncode": result.returncode,
                    "failures": accounting["failure_count"] if accounting else None,
                    "failed_cases": sorted(set(_FAILED_CASE.findall(output))),
                    "complete": diagnostic_complete,
                    "result_state": accounting["result_state"] if accounting else None,
                    "accounting_error": accounting_error,
                    "output_tail": output[-1500:],
                    "used_fresh_tree": interpreter != python,
                })
            except subprocess.TimeoutExpired as error:
                output = _output_text(error.stdout) + _output_text(error.stderr)
                attempt_results.append({
                    "returncode": None,
                    "failures": None,
                    "failed_cases": [],
                    "complete": False,
                    "timed_out": True,
                    "result_state": None,
                    "output_tail": output[-1500:],
                    "used_fresh_tree": interpreter != python,
                })
            except OSError as error:
                attempt_results.append({
                    "returncode": None,
                    "failures": None,
                    "failed_cases": [],
                    "complete": False,
                    "process_error": str(error),
                    "result_state": None,
                    "output_tail": "",
                    "used_fresh_tree": interpreter != python,
                })
        initial = attempt_results[0]
        findings[name] = {
            "initial_suite_failure": True,
            "returncode": initial["returncode"],
            "failures": initial["failures"],
            "failed_cases": sorted({
                case
                for attempt_result in attempt_results
                if attempt_result["complete"]
                and attempt_result["returncode"] == 2
                and attempt_result["result_state"] == "FAILURE"
                for case in attempt_result["failed_cases"]
            }),
            "attempts": attempt_results,
            "attempt_count": len(attempt_results),
            "used_fresh_tree": any(
                attempt_result["used_fresh_tree"] for attempt_result in attempt_results
            ),
            "output_tail": initial["output_tail"],
        }
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
        if name in file_cases:
            observed_cases = set(finding.get("failed_cases", []))
            attempts = finding.get("attempts", [])
            complete_attempts = bool(attempts) and all(
                attempt.get("complete") for attempt in attempts
            )
            if observed_cases and observed_cases <= file_cases[name] and complete_attempts:
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
    classification = report.get("classification")
    classified = (
        isinstance(classification, dict)
        and isinstance(classification.get("unexpected_failures"), list)
        and isinstance(classification.get("accepted_exclusions"), list)
    )
    unexpected = (
        classification["unexpected_failures"]
        if classified
        else ["suite classification missing or incomplete"]
    )
    status = report.get("returncode")
    failures = report.get("failure_count")
    failed_files = report.get("failed_files")
    complete = report.get("complete") is True
    status_ok = (
        status == 0
        and report.get("result_state") == "SUCCESS"
        and failures == 0
        and failed_files == []
    ) or (
        status == 2
        and report.get("result_state") == "FAILURE"
        and isinstance(failures, int)
        and failures >= 0
        and bool(failed_files)
    )
    files_run = report.get("test_files_run")
    files_expected = report.get("test_files_expected")
    try:
        tests_executed = int(str(report.get("tests_run", "0")).replace(",", ""))
    except ValueError:
        tests_executed = 0
    accounting_ok = (
        tests_executed > 0
        and isinstance(files_run, int)
        and isinstance(files_expected, int)
        and files_run > 0
        and files_run == files_expected
    )
    return {
        "tests_run": report["tests_run"],
        "failure_count": report["failure_count"],
        "failed_files": report["failed_files"],
        "test_files_run": report.get("test_files_run"),
        "test_files_expected": report.get("test_files_expected"),
        "returncode": status,
        "result_state": report.get("result_state"),
        "complete": complete,
        "accepted_exclusions": (
            classification["accepted_exclusions"] if classified else []
        ),
        "exclusions": [
            {"test": e.test, "reason": e.reason, "consequence": e.consequence}
            for e in (*FILE_EXCLUSIONS, *CASE_EXCLUSIONS)
        ],
        "unexpected_failures": unexpected,
        "ok": complete and accounting_ok and status_ok and classified and not unexpected,
    }
