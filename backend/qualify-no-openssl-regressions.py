from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO))

from buildsys.product import PRODUCT
from buildsys.package import copy_product_tree


RUNTIME_FILES = (
    Path("bin") / PRODUCT.interpreter_name,
    PRODUCT.stdlib_relative_path / "ssl.py",
    PRODUCT.stdlib_relative_path / "_ssl.py",
    PRODUCT.stdlib_relative_path / "_ssl_metadata.py",
    PRODUCT.stdlib_relative_path / "_hashlib.py",
    PRODUCT.stdlib_relative_path / "lib-dynload" / "_hashlib_graviola.abi3.so",
    PRODUCT.stdlib_relative_path / "python-build-cacert.pem",
)

RUNTIME_IDENTITY_SCRIPT = r"""
import importlib
import json
import platform
from pathlib import Path
import ssl
import sys
import sysconfig

prefix = Path(sys.prefix).resolve()
module_names = (
    "ssl",
    "_ssl",
    "_ssl_metadata",
    "_hashlib",
    "_hashlib_graviola",
    "rtls",
    "rtls._rustls",
)
modules = {}
for name in module_names:
    module = importlib.import_module(name)
    origin = Path(module.__file__).resolve()
    try:
        modules[name] = origin.relative_to(prefix).as_posix()
    except ValueError:
        modules[name] = "external:" + str(origin)

print(json.dumps({
    "version": sys.version,
    "implementation": sys.implementation.name,
    "implementation_version": list(sys.implementation.version),
    "cache_tag": sys.implementation.cache_tag,
    "abiflags": sys.abiflags,
    "maxsize": sys.maxsize,
    "platform": sys.platform,
    "machine": platform.machine(),
    "soabi": sysconfig.get_config_var("SOABI"),
    "multiarch": sysconfig.get_config_var("MULTIARCH"),
    "config_args": sysconfig.get_config_var("CONFIG_ARGS").replace(str(prefix), "{prefix}"),
    "ssl_backend": ssl.OPENSSL_VERSION,
    "module_origins": modules,
}, sort_keys=True))
"""


class QualificationError(Exception):
    pass


def positive_integer(value: str) -> int:
    try:
        result = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if result < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return result


def common_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip()).resolve().parent


def work_path(value: Path, root: Path, *, label: str, no_spaces: bool) -> Path:
    result = Path(value).resolve()
    work_root = root / ".work"
    if not result.is_relative_to(work_root):
        raise QualificationError(f"{label} must be under {work_root}: {result}")
    if no_spaces and any(character.isspace() for character in str(result)):
        raise QualificationError(f"{label} must not contain whitespace: {result}")
    return result


def runtime_files(prefix: Path) -> dict[str, str]:
    from buildsys.targets import native_target

    target = native_target()
    shared_library_suffix = ".dylib" if target.is_macos else ".so.1.0"
    expected = {prefix / relative for relative in RUNTIME_FILES}
    expected.add(
        prefix / "lib" / f"lib{PRODUCT.shared_library_stem}{shared_library_suffix}"
    )
    rtls = prefix / PRODUCT.stdlib_relative_path / "rtls"
    if not rtls.is_dir():
        raise QualificationError(f"runtime package is missing: {rtls}")
    for path in rtls.rglob("*"):
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_file() or path.is_symlink():
            expected.add(path)

    files = {}
    for path in sorted(expected):
        if not path.is_file() and not path.is_symlink():
            raise QualificationError(f"runtime identity file is missing: {path}")
        relative = path.relative_to(prefix).as_posix()
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def runtime_identity(prefix: Path, scratch: Path) -> dict[str, object]:
    from buildsys.product_process import run_product_process

    process = run_product_process(
        [
            str(PRODUCT.interpreter(prefix)),
            "-I",
            "-S",
            "-B",
            "-c",
            RUNTIME_IDENTITY_SCRIPT,
        ],
        prefix,
        scratch,
        timeout_seconds=30,
    )
    if process.returncode:
        raise QualificationError(
            f"runtime identity process failed for {prefix}: "
            f"{process.stdout}{process.stderr}"
        )
    try:
        runtime = json.loads(process.stdout)
    except json.JSONDecodeError as error:
        raise QualificationError(
            f"runtime identity output is invalid for {prefix}: {process.stdout!r}"
        ) from error
    if not runtime["ssl_backend"].startswith("Rustls "):
        raise QualificationError(
            f"runtime identity reports a non-Rustls TLS backend: {runtime['ssl_backend']}"
        )
    return {"runtime": runtime, "files": runtime_files(prefix)}


def ssl_test_case_inventory(prefix: Path, scratch: Path) -> dict[str, object]:
    from buildsys.product_process import run_product_process

    test_source = prefix / PRODUCT.stdlib_relative_path / "test" / "test_ssl.py"
    if test_source.is_symlink() or not test_source.is_file():
        raise QualificationError(f"CPython test_ssl source is missing or linked: {test_source}")
    source_root = prefix.resolve(strict=True)
    resolved_source = test_source.resolve(strict=True)
    if not resolved_source.is_relative_to(source_root):
        raise QualificationError(f"CPython test_ssl source escapes the prefix: {test_source}")
    inventory_script = r"""
import hashlib
import json
import unittest
from pathlib import Path
from test import test_ssl

def cases(suite):
    for case in suite:
        if isinstance(case, unittest.TestSuite):
            yield from cases(case)
        else:
            yield case.id()

suite = unittest.defaultTestLoader.loadTestsFromModule(test_ssl)
identifiers = list(cases(suite))
encoded = json.dumps(identifiers, separators=(",", ":")).encode()
print(json.dumps({
    "module_path": str(Path(test_ssl.__file__).resolve()),
    "test_count": suite.countTestCases(),
    "case_ids_sha256": hashlib.sha256(encoded).hexdigest(),
}, sort_keys=True))
"""
    process = run_product_process(
        [PRODUCT.interpreter(prefix), "-I", "-B", "-c", inventory_script],
        prefix,
        scratch,
        timeout_seconds=30,
    )
    if process.returncode:
        raise QualificationError(
            f"test_ssl case discovery failed for {prefix}: {process.stdout}{process.stderr}"
        )
    try:
        observed = json.loads(process.stdout)
    except json.JSONDecodeError as error:
        raise QualificationError(
            f"test_ssl case discovery returned invalid JSON: {process.stdout!r}"
        ) from error
    if not isinstance(observed, dict):
        raise QualificationError(f"test_ssl case discovery returned a non-object: {observed!r}")
    test_count = observed.get("test_count")
    module_path = observed.get("module_path")
    case_digest = observed.get("case_ids_sha256")
    if (
        type(test_count) is not int
        or test_count <= 0
        or module_path != str(resolved_source)
        or not isinstance(case_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", case_digest) is None
    ):
        raise QualificationError(f"test_ssl case discovery is incomplete: {observed!r}")
    return {
        "source_path": str(resolved_source),
        "source_sha256": hashlib.sha256(resolved_source.read_bytes()).hexdigest(),
        "test_count": test_count,
        "case_ids_sha256": case_digest,
    }


def verbose_command(argv) -> list[str]:
    command = [os.fspath(argument) for argument in argv]
    try:
        marker = command.index("test")
    except ValueError as error:
        raise QualificationError(
            "run_suite command did not invoke the test runner"
        ) from error
    if marker < 2 or command[marker - 1] != "-m":
        raise QualificationError("run_suite command has an unexpected test runner shape")
    command.insert(marker + 1, "-v")
    return command


def capture_suite(
    testsuite,
    python: Path,
    jobs: int,
    timeout: int,
    scratch: Path,
    log_path: Path,
):
    original_process = testsuite.run_product_process
    output = ""
    command = None

    def run_verbose(argv, *args, **kwargs):
        nonlocal output, command
        command = verbose_command(argv)
        try:
            result = original_process(command, *args, **kwargs)
        except subprocess.TimeoutExpired as error:
            stdout = error.stdout or ""
            stderr = error.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode(errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode(errors="replace")
            output = stdout + stderr
            log_path.write_text(output, encoding="utf-8")
            raise
        output = (result.stdout or "") + (result.stderr or "")
        log_path.write_text(output, encoding="utf-8")
        return result

    testsuite.run_product_process = run_verbose
    previous_scratch = testsuite.SCRATCH_ROOT
    testsuite.SCRATCH_ROOT = scratch
    try:
        accounting = testsuite.run_suite(
            python,
            jobs=jobs,
            per_test_timeout=timeout,
        )
    finally:
        testsuite.run_product_process = original_process
        testsuite.SCRATCH_ROOT = previous_scratch
    if command is not None:
        accounting["command"] = " ".join(command)
    return accounting, output


def log_record(path: Path) -> dict[str, str]:
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def write_report(path: Path, report: dict) -> None:
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run(args) -> int:
    from buildsys import testsuite
    from buildsys.targets import native_target

    target = native_target()
    if target.triple not in {
        "aarch64-apple-darwin",
        "aarch64-unknown-linux-musl",
        "x86_64-unknown-linux-musl",
    }:
        raise QualificationError(
            f"this experimental regression check supports native macOS arm64 and Linux musl targets only: {target.triple}"
        )
    root = common_root()
    source_prefix = work_path(args.prefix, root, label="prefix", no_spaces=False)
    if not source_prefix.is_dir():
        raise QualificationError(f"prefix does not exist: {source_prefix}")
    run_dir = work_path(args.run_dir, REPO, label="run directory", no_spaces=True)
    if run_dir == source_prefix or run_dir.is_relative_to(source_prefix):
        raise QualificationError("run directory must not be inside the source prefix")
    if run_dir.exists() and any(run_dir.iterdir()):
        raise QualificationError(f"run directory is not empty: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    work_dir = run_dir
    if args.work_dir is not None:
        work_dir = work_path(args.work_dir, REPO, label="work directory", no_spaces=True)
        if (
            work_dir == source_prefix
            or work_dir.is_relative_to(source_prefix)
            or source_prefix.is_relative_to(work_dir)
            or work_dir == run_dir
            or work_dir.is_relative_to(run_dir)
            or run_dir.is_relative_to(work_dir)
        ):
            raise QualificationError("external work directory overlaps the candidate or reports")
        if work_dir.exists() and any(work_dir.iterdir()):
            raise QualificationError(f"work directory is not empty: {work_dir}")
        work_dir.mkdir(parents=True, exist_ok=True)
    scratch = work_dir / ("t" if args.work_dir is not None else "scratch")
    scratch.mkdir()
    tested_prefix = work_dir / ("p" if args.work_dir is not None else "python")
    report_path = run_dir / "report.json"
    full_suite_log = run_dir / "full-suite.log"
    test_ssl_log = run_dir / "test_ssl.log"
    report = {
        "complete": False,
        "ok": False,
        "candidate_prefix": str(source_prefix),
        "tested_prefix": str(tested_prefix),
        "execution_directory": str(scratch),
        "candidate_identity": {},
        "tested_identity": {},
        "runtime_identity": {},
        "ssl_test_inventory": {},
        "diagnostics": {},
        "solo_findings": {},
    }

    try:
        source_identity = runtime_identity(source_prefix, scratch)
        source_test_inventory = ssl_test_case_inventory(source_prefix, scratch)
        policy = importlib.import_module("regression_policy")
        expected_ssl_test_count = policy.EXPECTED_SSL_TEST_COUNT
        copy_product_tree(source_prefix, tested_prefix)
        tested_identity = runtime_identity(tested_prefix, scratch)
        tested_test_inventory = ssl_test_case_inventory(tested_prefix, scratch)
        inventories_equal = all(
            source_test_inventory[key] == tested_test_inventory[key]
            for key in ("source_sha256", "test_count", "case_ids_sha256")
        )
        report["ssl_test_inventory"] = {
            "candidate": source_test_inventory,
            "tested": tested_test_inventory,
            "expected_test_count": expected_ssl_test_count,
            "candidate_count_matches_expected": (
                source_test_inventory["test_count"] == expected_ssl_test_count
            ),
            "tested_count_matches_expected": (
                tested_test_inventory["test_count"] == expected_ssl_test_count
            ),
            "equal": inventories_equal,
        }
        report["candidate_identity"] = source_identity["files"]
        report["tested_identity"] = tested_identity["files"]
        report["runtime_identity"] = {
            "candidate": source_identity["runtime"],
            "tested": tested_identity["runtime"],
            "equal": source_identity["runtime"] == tested_identity["runtime"],
        }
        if source_identity != tested_identity:
            raise QualificationError("copied prefix runtime identity changed")
        if not inventories_equal:
            raise QualificationError("copied test_ssl source or discovered cases changed")

        try:
            accounting, full_output = capture_suite(
                testsuite,
                PRODUCT.interpreter(tested_prefix),
                args.jobs,
                args.timeout,
                scratch,
                full_suite_log,
            )
            report.update(accounting)
        except Exception as error:
            report["suite_error"] = f"{type(error).__name__}: {error}"
            full_output = (
                full_suite_log.read_text(encoding="utf-8")
                if full_suite_log.exists()
                else ""
            )

        if full_suite_log.exists():
            report["diagnostics"]["full_suite_log"] = log_record(full_suite_log)
        if full_output:
            extracted = policy.extract_test_ssl_log(full_output)
            if not isinstance(extracted, str) or not extracted:
                raise QualificationError("test_ssl extraction returned no verbose output")
            test_ssl_log.write_text(extracted, encoding="utf-8")
            assessment = policy.assess_ssl_full_run(
                full_output,
                expected_tests_run=expected_ssl_test_count,
            )
            if not isinstance(assessment, dict):
                raise QualificationError("test_ssl assessment did not return an object")
            assessment = dict(assessment)
            test_ssl_record = log_record(test_ssl_log)
            policy_path = Path(policy.__file__).resolve()
            assessment.update(
                {
                    "source_log_path": test_ssl_record["path"],
                    "source_log_sha256": test_ssl_record["sha256"],
                    "policy_path": str(policy_path),
                    "policy_sha256": hashlib.sha256(
                        policy_path.read_bytes()
                    ).hexdigest(),
                }
            )
            report["diagnostics"]["test_ssl_log"] = test_ssl_record
            policy_source = REPO / policy.POLICY_SOURCE
            report["modern_policy"] = {
                "policy_path": str(policy_source),
                "policy_sha256": hashlib.sha256(
                    policy_source.read_bytes()
                ).hexdigest(),
                "ssl_exact_case_assessment": assessment,
            }

        if "returncode" in report:
            accounting = report
            failed_files = set(accounting["failed_files"])
            solo_names = failed_files - {"test_ssl"}
            original_process = testsuite.run_product_process

            def run_diagnostic(argv, install, cwd, **kwargs):
                return original_process(argv, install, scratch, **kwargs)

            testsuite.run_product_process = run_diagnostic
            try:
                solo_findings = testsuite.verify_excluded_failures(
                    PRODUCT.interpreter(tested_prefix),
                    sorted(solo_names),
                    attempts=1,
                    target=target,
                )
            finally:
                testsuite.run_product_process = original_process
            if set(solo_findings) != solo_names:
                raise QualificationError("solo findings do not match non-SSL failed files")
            classification = testsuite.classify(solo_findings, target)
            report["solo_findings"] = solo_findings
            report["classification"] = classification
            assessment = report.get("modern_policy", {}).get(
                "ssl_exact_case_assessment", {}
            )
            report["ok"] = bool(
                accounting["complete"]
                and accounting["returncode"] in (0, 2)
                and not classification["unexpected_failures"]
                and isinstance(assessment, dict)
                and assessment.get("complete") is True
                and assessment.get("ok") is True
            )
        else:
            report["ok"] = False
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        report["ok"] = False

    if full_suite_log.exists():
        report["diagnostics"].setdefault("full_suite_log", log_record(full_suite_log))
    if test_ssl_log.exists():
        report["diagnostics"].setdefault("test_ssl_log", log_record(test_ssl_log))
    write_report(report_path, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Run controlled CPython regressions against an OpenSSL-free prefix"
    )
    parser.add_argument("--prefix", required=True, type=Path)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--jobs", default=6, type=positive_integer)
    parser.add_argument("--timeout", default=600, type=positive_integer)
    args = parser.parse_args(argv)
    try:
        return run(args)
    except Exception as error:
        print(f"FAIL OpenSSL-free regression qualification: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
