from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

class QualificationDriverError(Exception):
    pass


def require_work_path(path: Path, name: str) -> Path:
    resolved = Path(path).resolve()
    work_root = (REPO / ".work").resolve()
    if not resolved.is_relative_to(work_root) or resolved == work_root:
        raise QualificationDriverError(f"{name} must be inside {work_root}: {resolved}")
    return resolved


def require_product_work_path(path: Path, name: str) -> Path:
    resolved = Path(path).resolve()
    work_roots = ((REPO / ".work").resolve(), (COMMON_ROOT / ".work").resolve())
    if not any(resolved.is_relative_to(root) and resolved != root for root in work_roots):
        raise QualificationDriverError(
            f"{name} must be inside a repository .work directory: {resolved}"
        )
    return resolved


def common_repository_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    root = Path(result.stdout.strip()).resolve().parent
    for name in ("sources.lock.json", "bootstrap.lock.json"):
        if (REPO / name).read_bytes() != (root / name).read_bytes():
            raise QualificationDriverError(
                f"{name} differs from the shared toolchain and input lock owner"
            )
    return root


COMMON_ROOT = common_repository_root()
sys.path.insert(0, str(COMMON_ROOT))

from buildsys.package import PackageError, create_archive, qualify, verify_archive_extraction
from buildsys.product import PRODUCT
from buildsys.scope import ScopeError, prune_distribution_payload
from buildsys.standalone_compat import run_standalone_compatibility
from buildsys.targets import native_target
from buildsys.validate_product import run_validation, write_report


def load_research_driver():
    path = REPO / "research" / "rtls-graviola" / "build-no-openssl.py"
    spec = importlib.util.spec_from_file_location("no_openssl_build_driver", path)
    if spec is None or spec.loader is None:
        raise QualificationDriverError(f"cannot load research build driver: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_package_driver():
    path = COMMON_ROOT / "build" / "package.py"
    spec = importlib.util.spec_from_file_location("python_build_package_driver", path)
    if spec is None or spec.loader is None:
        raise QualificationDriverError(f"cannot load package helpers: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def check_result(ok: bool, **values) -> dict:
    return {"ok": ok, **values}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Archive and validate an existing no-OpenSSL candidate prefix"
    )
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--build-run-dir", type=Path)
    parser.add_argument("--run-dir", type=Path, required=True)
    arguments = parser.parse_args(argv)

    try:
        source_prefix = require_product_work_path(arguments.prefix, "candidate prefix")
        run_dir = require_work_path(arguments.run_dir, "qualification run directory")
        build_run_dir = require_product_work_path(
            arguments.build_run_dir or source_prefix.parent, "candidate build directory"
        )
        if not source_prefix.is_dir():
            raise QualificationDriverError(f"candidate prefix does not exist: {source_prefix}")
        if run_dir.exists():
            raise QualificationDriverError(f"refusing to replace qualification directory: {run_dir}")
        if run_dir.is_relative_to(source_prefix) or source_prefix.is_relative_to(run_dir):
            raise QualificationDriverError("candidate prefix and qualification directory overlap")
        target = native_target()
        if target.triple != "aarch64-apple-darwin":
            raise QualificationDriverError(
                f"this experimental qualification is native macOS arm64 only: {target.triple}"
            )
        if not PRODUCT.interpreter(source_prefix).is_file():
            raise QualificationDriverError(
                f"candidate interpreter is missing: {PRODUCT.interpreter(source_prefix)}"
            )
        run_dir.mkdir(parents=True)
        package_work = run_dir / "prepared package tree"
        extracted_parent = run_dir / "archive validation with spaces"
        validation_work = run_dir / "native product validation"
        compatibility_work = run_dir / "standalone compatibility scratch"
        host_tmp = run_dir / "host temporary files"
        for path in (validation_work, compatibility_work, host_tmp):
            path.mkdir()
        tempfile.tempdir = str(host_tmp)

        report: dict = {
            "candidate_prefix": str(source_prefix),
            "candidate_build_directory": str(build_run_dir),
            "target": target.triple,
            "shared_lock_root": str(COMMON_ROOT),
            "scope": {
                "result_is_production_qualification": False,
                "full_cpython_regression_suite": "not run",
                "production_pgo": "not built or checked",
                "minimum_macos_runtime": "not tested",
                "host_macos_version": platform.mac_ver()[0],
            },
            "checks": {},
        }

        shutil.copytree(source_prefix, package_work, symlinks=True)
        report["checks"]["private_package_copy"] = check_result(
            True, path=str(package_work), source_preserved=True
        )

        research_driver = load_research_driver()
        try:
            research_driver.verify_overlay_prefix(package_work, build_run_dir, target)
            report["checks"]["no_openssl_overlay"] = check_result(True)
        except Exception as error:
            report["checks"]["no_openssl_overlay"] = check_result(
                False, error_type=type(error).__name__, error=str(error)
            )

        package_driver = load_package_driver()
        package_driver.REPO = COMMON_ROOT

        try:
            stripped = package_driver.strip_tree_macos(package_work)
            report["checks"]["strip"] = check_result(
                True, mach_o_images_stripped=len(stripped)
            )
        except Exception as error:
            report["checks"]["strip"] = check_result(
                False, error_type=type(error).__name__, error=str(error)
            )

        try:
            report["checks"]["distribution_prune"] = prune_distribution_payload(package_work)
        except (ScopeError, OSError) as error:
            report["checks"]["distribution_prune"] = check_result(
                False, error_type=type(error).__name__, error=str(error)
            )

        archive_path = run_dir / "experimental no-openssl candidate.tar.gz"
        try:
            archive_facts = create_archive(package_work, archive_path)
            extracted = verify_archive_extraction(package_work, archive_path, extracted_parent)
            report["checks"]["archive_roundtrip"] = check_result(
                True,
                archive=str(archive_path),
                archive_sha256=archive_facts.sha256,
                archive_size_bytes=archive_facts.size_bytes,
                payload_sha256=archive_facts.payload_sha256,
                payload_size_bytes=archive_facts.payload_size_bytes,
                extracted_prefix=str(extracted),
            )
        except (PackageError, OSError) as error:
            report["checks"]["archive_roundtrip"] = check_result(
                False, error_type=type(error).__name__, error=str(error)
            )
            report["ok"] = False
            report_path = run_dir / "qualification report.json"
            write_report(report, report_path)
            print(f"REPORT {report_path}")
            return 1

        validation = run_validation(extracted, validation_work, target)
        report["validation"] = validation
        try:
            import buildsys.standalone_compat as standalone_compat

            standalone_compat.SCRATCH_ROOT = compatibility_work
            compatibility = run_standalone_compatibility(
                PRODUCT.interpreter(extracted), extracted, target
            )
        except Exception as error:
            compatibility = {
                "ok": False,
                "checks": {
                    "aggregate": {
                        "status": "failed",
                        "error_type": type(error).__name__,
                        "error": str(error),
                    }
                },
            }
        report["compatibility"] = compatibility
        report["qualification"] = qualify(
            validation,
            compatibility,
            additional_checks={
                name: result
                for name, result in report["checks"].items()
            },
        )
        report["ok"] = report["qualification"]["ok"]
        report_path = run_dir / "qualification report.json"
        write_report(report, report_path)
        failures = sorted(
            name
            for name, value in report["qualification"]["checks"].items()
            if value.get("status") == "failed"
        )
        print(f"REPORT {report_path}")
        print(f"ARCHIVE {archive_path}")
        print(f"EXPERIMENTAL ARCHIVE CHECKS {'PASS' if report['ok'] else 'FAIL'}")
        for failure in failures:
            detail = report["qualification"]["checks"][failure]
            print(f"FAIL {failure}: {detail.get('error', detail)}")
        return 0 if report["ok"] else 1
    except Exception as error:
        print(f"FAIL qualification driver: {type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
