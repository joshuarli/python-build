from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO))

from buildsys.product import PRODUCT


RUNTIME_FILES = (
    Path("bin") / PRODUCT.interpreter_name,
    Path("lib") / f"lib{PRODUCT.shared_library_stem}.dylib",
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
    expected = {prefix / relative for relative in RUNTIME_FILES}
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
    if target.triple != "aarch64-apple-darwin":
        raise QualificationError(
            f"this experimental regression check is native macOS arm64 only: {target.triple}"
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
    scratch = run_dir / "scratch"
    scratch.mkdir()
    tested_prefix = run_dir / "python"
    report_path = run_dir / "report.json"
    full_suite_log = run_dir / "full-suite.log"
    test_ssl_log = run_dir / "test_ssl.log"
    report = {
        "complete": False,
        "ok": False,
        "candidate_prefix": str(source_prefix),
        "tested_prefix": str(tested_prefix),
        "candidate_identity": {},
        "tested_identity": {},
        "runtime_identity": {},
        "diagnostics": {},
        "solo_findings": {},
    }

    try:
        source_identity = runtime_identity(source_prefix, scratch)
        shutil.copytree(
            source_prefix,
            tested_prefix,
            symlinks=True,
            copy_function=shutil.copy2,
        )
        tested_identity = runtime_identity(tested_prefix, scratch)
        report["candidate_identity"] = source_identity["files"]
        report["tested_identity"] = tested_identity["files"]
        report["runtime_identity"] = {
            "candidate": source_identity["runtime"],
            "tested": tested_identity["runtime"],
            "equal": source_identity["runtime"] == tested_identity["runtime"],
        }
        if source_identity != tested_identity:
            raise QualificationError("copied prefix runtime identity changed")

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
            policy = importlib.import_module("regression_policy")
            extracted = policy.extract_test_ssl_log(full_output)
            if not isinstance(extracted, str) or not extracted:
                raise QualificationError("test_ssl extraction returned no verbose output")
            test_ssl_log.write_text(extracted, encoding="utf-8")
            assessment = policy.assess_ssl_full_run(full_output)
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
            solo_findings = testsuite.verify_excluded_failures(
                PRODUCT.interpreter(tested_prefix),
                sorted(solo_names),
                attempts=1,
                target=target,
            )
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
