"""Qualify and publish an artifact from the staged install tree."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from buildsys import macho
from buildsys.bootstrap import load_macos_toolchain
from buildsys.ca_bundle import CABundleError, install_fallback_ca_bundle
from buildsys.elf import gnu_stack_report, hardening_report
from buildsys.inputs import InputError, load_lock
from buildsys.package import (
    PackageError,
    build_manifest,
    create_archive,
    publish_files,
    qualify,
    validate_build_record,
    verify_archive_extraction,
    write_manifest,
)
from buildsys.patches import PatchError, apply_patch
from buildsys.product import PRODUCT
from buildsys.relocate import find_elfs
from buildsys.scope import ScopeError, prune_distribution_payload
from buildsys.standalone_compat import CompatibilityError, run_standalone_compatibility
from buildsys.targets import Target, native_target
from buildsys.testsuite import (
    SuiteError,
    classify,
    report_payload,
    run_suite,
    verify_excluded_failures,
)
from buildsys.validate_macos import ValidationError, run_validation

TARGET_DESCRIPTION = native_target()
TARGET = TARGET_DESCRIPTION.triple
REVISION = "r2"
ARCHIVE_NAME = PRODUCT.local_archive_name(TARGET, REVISION)

class PackagingError(Exception):
    """The staged tree could not be qualified and published."""


def _run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(command, capture_output=True, text=True, **kwargs)
    except (OSError, subprocess.SubprocessError) as error:
        raise PackagingError(f"could not run {command}: {error}") from error
    if result.returncode != 0:
        raise PackagingError(f"{command}: {result.stderr or result.stdout}")
    return result


def strip_tree(install: Path, *, strip: str = "llvm-strip") -> list[Path]:
    stripped = []
    for elf in find_elfs(install):
        _run([strip, "--strip-unneeded", str(elf)])
        stripped.append(elf)
    return stripped


def strip_tree_macos(install: Path) -> list[Path]:
    locked = load_macos_toolchain(REPO / "bootstrap.lock.json")
    strip = locked.llvm_prefix / "bin" / "llvm-strip"
    stripped = []
    for image in macho.find_machos(install):
        _run([str(strip), "--strip-debug", str(image)])
        macho.sign_adhoc(image)
        stripped.append(image)
    return stripped


def require_macos_pgo_recipe() -> dict:
    recipe_path = REPO / "build" / "logs" / "cpython-build.json"
    try:
        recipe = json.loads(recipe_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise PackagingError(f"macOS PGO build recipe is missing or invalid: {error}") from error
    optimization = recipe.get("optimization", {})
    jobs = optimization.get("pgo_jobs")
    if recipe.get("target") != TARGET or not optimization.get("pgo"):
        raise PackagingError("staged macOS build has no matching PGO recipe")
    if type(jobs) is not int or jobs < 1:
        raise PackagingError("macOS PGO recipe has no valid worker count")
    from buildsys.cpython import CPYTHON_PGO_HASH_SEED, pgo_profile_task

    if optimization.get("profile_task") != pgo_profile_task(jobs):
        raise PackagingError("macOS PGO recipe has an unexpected PROFILE_TASK")
    if recipe.get("environment", {}).get("PYTHONHASHSEED") != CPYTHON_PGO_HASH_SEED:
        raise PackagingError("macOS PGO recipe has no fixed Python hash seed")
    profile_data = optimization.get("profile_data", {})
    profile_hash = profile_data.get("sha256")
    profile_size = profile_data.get("size_bytes")
    if (
        profile_data.get("path") != "code.profclangd"
        or not isinstance(profile_hash, str)
        or not re.fullmatch(r"[0-9a-f]{64}", profile_hash)
        or type(profile_size) is not int
        or profile_size < 1
    ):
        raise PackagingError("macOS PGO recipe has no valid merged profile receipt")
    if not Path(optimization.get("llvm_profdata", "")).is_file():
        raise PackagingError("macOS PGO recipe's llvm-profdata is not present")
    source = recipe.get("source", {})
    cpython = [entry for entry in load_lock(REPO / "sources.lock.json") if entry.name == "cpython"]
    if len(cpython) != 1:
        raise PackagingError("source lock must contain exactly one CPython pin")
    pin = cpython[0]
    if (source.get("name"), source.get("version"), source.get("sha256")) != (
        pin.name, pin.version, pin.sha256
    ):
        raise PackagingError("macOS PGO recipe does not match the locked CPython source")
    if "-fno-omit-frame-pointer" in recipe.get("environment", {}).get("CFLAGS", ""):
        raise PackagingError("macOS PGO recipe unexpectedly retains frame pointers")
    return recipe


def install_ca_fallback(install: Path) -> dict[str, object]:
    ssl_module = PRODUCT.stdlib(install) / "ssl.py"
    if not ssl_module.is_file():
        raise PackagingError(f"installed ssl module is missing: {ssl_module}")
    if "_PYTHON_BUILD_DEFAULT_CA_BUNDLE" not in ssl_module.read_text():
        patch = REPO / "patches" / "package" / "0001-ssl-default-ca-bundle-fallback.patch"
        try:
            apply_patch(ssl_module.parent, patch, strip=2)
        except PatchError as error:
            raise PackagingError(f"cannot enable the locked CA fallback: {error}") from error
    try:
        return install_fallback_ca_bundle(
            install, cache_root=REPO / ".cache", lock_path=REPO / "sources.lock.json"
        )
    except CABundleError as error:
        raise PackagingError(str(error)) from error


def _linux_validation(install: Path) -> dict:
    checks: dict[str, dict] = {}
    python = PRODUCT.interpreter(install)
    imports = subprocess.run(
        [str(python), "-I", "-B", "-c", "import ssl, sqlite3, dbm, compression.zstd"],
        capture_output=True,
        text=True,
    )
    checks["smoke_import"] = {
        "ok": imports.returncode == 0,
        "output": (imports.stdout + imports.stderr).strip(),
    }

    elfs = find_elfs(install)
    if not elfs:
        raise PackagingError("packaged tree contains no ELF files")
    forbidden = []
    stack_violations = []
    elf_report = []
    for elf in elfs:
        dynamic = _run(["readelf", "-d", str(elf)]).stdout
        needed = [
            line.split("[")[1].rstrip("]")
            for line in dynamic.splitlines()
            if "NEEDED" in line
        ]
        if any(name.startswith("libc.so.6") or "GLIBC" in name for name in needed):
            forbidden.append(str(elf.relative_to(install)))
        stack = gnu_stack_report(_run(["readelf", "-lW", str(elf)]).stdout)
        if not stack["ok"]:
            stack_violations.append(str(elf.relative_to(install)))
        elf_report.append({
            "path": str(elf.relative_to(install)),
            "needed": needed,
            "gnu_stack": stack,
        })
    checks["elf_linkage"] = {
        "ok": not forbidden,
        "forbidden_needed": forbidden,
        "elf_report": elf_report,
    }
    checks["elf_stack"] = {
        "ok": not stack_violations,
        "violations": stack_violations,
    }

    interpreter = PRODUCT.interpreter(install)
    interp = _run(["readelf", "-l", str(interpreter)]).stdout
    interp_line = next((line for line in interp.splitlines() if "interpreter" in line), "")
    checks["musl_loader"] = {
        "ok": TARGET_DESCRIPTION.musl_loader in interp_line,
        "actual": interp_line.strip(),
        "expected": TARGET_DESCRIPTION.musl_loader,
    }
    sysconfig = subprocess.run(
        [str(interpreter), "-I", "-B", "-c", "import sysconfig; print(sysconfig.get_config_var('LDFLAGS') or '')"],
        capture_output=True,
        text=True,
    )
    checks["sysconfig_paths"] = {
        "ok": sysconfig.returncode == 0 and "build/prefix" not in sysconfig.stdout,
        "output": (sysconfig.stdout + sysconfig.stderr).strip(),
    }
    configured = _run([
        str(interpreter), "-I", "-B", "-c",
        "import json,sysconfig; print(json.dumps({k: sysconfig.get_config_var(k) "
        "for k in ('CFLAGS','CFLAGS_NODIST','PY_CFLAGS','PY_CFLAGS_NODIST','CPPFLAGS')}))",
    ])
    flag_values = json.loads(configured.stdout.strip().splitlines()[-1])
    symbols = {
        "interpreter": _run(["readelf", "--dyn-syms", "-W", str(interpreter)]).stdout,
        "libpython": _run([
            "readelf", "--dyn-syms", "-W",
            str(install / "lib" / _run([
                str(interpreter), "-I", "-B", "-c",
                "import sysconfig; print(sysconfig.get_config_var('INSTSONAME'))",
            ]).stdout.strip()),
        ]).stdout,
    }
    hardening = hardening_report(
        " ".join(value for value in flag_values.values() if isinstance(value, str)),
        symbols,
    )
    checks["elf_hardening"] = hardening
    failed = sorted(name for name, result in checks.items() if result.get("ok") is not True)
    return {"ok": not failed, "failed": failed, "checks": checks}


def _source_revision() -> str:
    result = _run(["git", "rev-parse", "HEAD"], cwd=REPO)
    revision = result.stdout.strip()
    if not revision:
        raise PackagingError("git returned an empty source revision")
    return revision


def _llvm_version(record: dict, lock_path: Path, target: Target) -> str:
    try:
        document = json.loads(lock_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise PackagingError(f"cannot read bootstrap lock: {error}") from error
    if target.is_macos:
        llvm_version = record["toolchain"]["llvm_version"]
    else:
        llvm_pins = [
            pin.split("=", 1)[1].rsplit("-r", 1)[0]
            for pin in document.get("explicitly_pinned_in_dockerfile", [])
            if pin.startswith("clang22=")
        ]
        if len(llvm_pins) != 1:
            raise PackagingError("bootstrap lock must pin one Linux LLVM toolchain")
        llvm_version = llvm_pins[0]
    return llvm_version


def _verify_install_matches_record(install: Path, record: dict) -> None:
    interpreter = PRODUCT.interpreter(install)
    probe = _run([
        str(interpreter), "-I", "-B", "-c",
        "import json,sysconfig; keys=('CFLAGS','CFLAGS_NODIST','PY_CFLAGS',"
        "'PY_CFLAGS_NODIST','LDFLAGS','LTOFLAGS','CONFIG_ARGS'); "
        "print(json.dumps({key:sysconfig.get_config_var(key) for key in keys}))",
    ])
    actual = json.loads(probe.stdout.strip().splitlines()[-1])
    if actual != record["effective_flags"]:
        raise PackagingError("staged install configuration does not match its build record")


def _macos_suite(install: Path, workdir: Path) -> dict:
    suite_tree = workdir / "regression-copy"
    shutil.copytree(install, suite_tree, symlinks=True)
    suite_python = PRODUCT.interpreter(suite_tree)

    def fresh_python() -> Path:
        retry_tree = workdir / "regression-retry"
        if retry_tree.exists():
            shutil.rmtree(retry_tree)
        shutil.copytree(install, retry_tree, symlinks=True)
        return PRODUCT.interpreter(retry_tree)

    suite = run_suite(suite_python)
    solo = verify_excluded_failures(
        suite_python, suite["failed_files"], fresh_python=fresh_python
    )
    suite["classification"] = classify(solo)
    report = report_payload(suite)
    report["solo_findings"] = {
        name: finding["failures"] for name, finding in solo.items()
    }
    return report


def _qualification(
    install: Path,
    workdir: Path,
    target: Target,
    *,
    trust_store: dict,
    distribution_scope: dict,
    regression_suite: dict | None,
) -> dict:
    python = PRODUCT.interpreter(install)
    if target.is_macos:
        validation = run_validation(install, workdir / "macos-validation", target)
    else:
        validation = _linux_validation(install)
    validation["checks"].update({
        "trust_store": {
            **trust_store,
            "ok": trust_store.get("ca_certificates", 0) > 0,
        },
        "distribution_scope": distribution_scope,
    })
    if regression_suite is not None:
        validation["checks"]["regression_suite"] = regression_suite
        if not regression_suite.get("ok"):
            validation.setdefault("failed", []).append("regression_suite")
            validation["ok"] = False
    compatibility = run_standalone_compatibility(python, install, target)
    return qualify(validation, compatibility)


def _package(*, qualify_only: bool = False) -> Path:
    stage = REPO / "build" / "stage" / "cpython-staged" / "install"
    if not stage.is_dir():
        raise PackagingError("no staged install; run `build` first")
    build_record = validate_build_record(
        stage.parent / "build-record.json",
        product=PRODUCT,
        target=TARGET_DESCRIPTION,
        lock_path=REPO / "sources.lock.json",
        bootstrap_lock_path=REPO / "bootstrap.lock.json",
        patches_directory=REPO / "patches" / "cpython",
    )
    if TARGET_DESCRIPTION.is_macos:
        require_macos_pgo_recipe()
    source_revision = _source_revision()
    archive_name = ARCHIVE_NAME

    scratch_root = REPO / ".work" / "tmp"
    scratch_root.mkdir(parents=True, exist_ok=True)
    output = REPO / "dist" / TARGET
    with tempfile.TemporaryDirectory(prefix="package-", dir=scratch_root) as temporary:
        workdir = Path(temporary)
        install = workdir / "install"
        shutil.copytree(stage, install, symlinks=True)
        _verify_install_matches_record(install, build_record)
        trust_store = install_ca_fallback(install)
        if TARGET_DESCRIPTION.is_macos:
            strip_tree_macos(install)
            regression_suite = _macos_suite(install, workdir)
        else:
            strip_tree(install)
            regression_suite = None
        try:
            distribution_scope = prune_distribution_payload(install)
        except ScopeError as error:
            raise PackagingError(str(error)) from error
        archive_temp = workdir / "artifact.tar.gz"
        facts = create_archive(install, archive_temp)
        extracted = verify_archive_extraction(
            install, archive_temp, workdir / "archive-check"
        )
        qualification = _qualification(
            extracted,
            workdir,
            TARGET_DESCRIPTION,
            trust_store=trust_store,
            distribution_scope=distribution_scope,
            regression_suite=regression_suite,
        )
        if not qualification["ok"]:
            failures = sorted(
                name for name, check in qualification["checks"].items()
                if check.get("status") == "failed"
            )
            raise PackagingError("qualification failed: " + ", ".join(failures))
        bootstrap_identity = build_record["bootstrap_identity"]
        llvm_version = _llvm_version(
            build_record, REPO / "bootstrap.lock.json", TARGET_DESCRIPTION
        )
        recipe_identity = build_record["recipe_identity"]
        if qualify_only:
            report = {
                "schema_version": 1,
                "product": {
                    "version": PRODUCT.version_string,
                    "abi_tag": PRODUCT.abi_tag,
                    "gil_enabled": True,
                },
                "target": TARGET,
                "source_revision": source_revision,
                "recipe_identity": recipe_identity,
                "bootstrap_identity": bootstrap_identity,
                "toolchain": {"llvm_version": llvm_version},
                "archive": {
                    "filename": archive_name,
                    "sha256": facts.sha256,
                    "size_bytes": facts.size_bytes,
                },
                "qualification": qualification,
            }
            report_temp = workdir / "qualification.json"
            report_temp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
            report_path = REPO / "build" / "qualification" / f"{TARGET}.json"
            publish_files({report_path: report_temp})
            return report_path
        manifest = build_manifest(
            product=PRODUCT,
            target=TARGET_DESCRIPTION,
            source_revision=source_revision,
            recipe_identity=recipe_identity,
            bootstrap_identity=bootstrap_identity,
            llvm_version=llvm_version,
            archive_filename=archive_name,
            archive=facts,
            qualification=qualification,
            lock_path=REPO / "sources.lock.json",
        )
        manifest_temp = workdir / "artifact.json"
        write_manifest(manifest_temp, manifest)
        publish_files({
            output / archive_name: archive_temp,
            output / "artifact.json": manifest_temp,
        })
    return output / archive_name


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Qualify and package the staged interpreter")
    parser.add_argument("--qualify-only", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        if arguments.qualify_only:
            report = _package(qualify_only=True)
            print(f"OK    qualify -> {report}")
            return 0
        archive = _package()
    except (
        PackagingError, PackageError, InputError, ScopeError, CompatibilityError,
        ValidationError, SuiteError,
    ) as error:
        print(f"FAIL package: {error}")
        return 1
    except Exception as error:
        print(f"FAIL package: {type(error).__name__}: {error}")
        return 1
    print(f"OK    package -> {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
