#!/usr/bin/env python3
"""Build and validate the isolated macOS Rust-for-CPython lane."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
LANE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from buildsys import macho  # noqa: E402
from buildsys.bootstrap import (  # noqa: E402
    BootstrapError,
    load_macos_toolchain,
    problems as toolchain_problems,
    sdk_version,
)
from buildsys.inputs import (  # noqa: E402
    Cache,
    Input,
    InputError,
    load_lock,
    safe_extract,
)
from buildsys.llvm import (  # noqa: E402
    extract_llvm_archive,
    verify_llvm_attestation_metadata,
)
from buildsys.sandbox import (  # noqa: E402
    SealedRun,
    SandboxError,
    available as sandbox_available,
    network_boundary_selftest,
)
from buildsys.targets import target_for_triple  # noqa: E402

TARGET = "aarch64-apple-darwin"
RUST_CHANNEL = "nightly-2026-09-15"
SOURCE_LOCK = LANE / "sources.lock.json"
PATCH_MANIFEST = LANE / "patches" / "manifest.json"
ZLIB_LOCK = LANE / "zlib-proof" / "sources.lock.json"
BOOTSTRAP_LOCK = REPO / "bootstrap.lock.json"
CACHE_ROOT = REPO / ".cache"
CARGO_HOME = LANE / ".cargo-home"
WORK = LANE / "work"
ZLIB_SOURCE = WORK / "zlib-candidate-source"
ZLIB_TARGET = WORK / "zlib-candidate-target"
ZLIB_ARCHIVE = ZLIB_TARGET / "release" / "libz_rs.a"
BUILD = WORK / "build"
SOURCE = WORK / "source"
STAGE = LANE / "stage"
LOGS = LANE / "logs"
RESULTS = LANE / "results"
BUILD_REPORT = RESULTS / "build.json"
SOURCE_DATE_EPOCH = "1704067200"
PROFILE_TASK = "-m test --pgo"


class LaneError(Exception):
    """The pinned experimental build lane cannot safely continue."""


def _read_lock() -> tuple[dict[str, Any], Input]:
    try:
        document = json.loads(SOURCE_LOCK.read_text())
        metadata = document["source"]
        entries = load_lock(SOURCE_LOCK)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, InputError) as error:
        raise LaneError(f"cannot read Rust-for-CPython source lock: {error}") from error
    if len(entries) != 1:
        raise LaneError(f"{SOURCE_LOCK}: expected exactly one source input")
    entry = entries[0]
    required = {
        "repository", "branch", "commit", "version", "license",
        "cargo_lock_sha256",
    }
    missing = sorted(required - metadata.keys())
    if missing:
        raise LaneError(f"{SOURCE_LOCK}: source metadata is missing {', '.join(missing)}")
    if (
        entry.name != "cpython-rust"
        or entry.version != metadata["version"]
        or entry.role != "build-source"
        or entry.target != TARGET
        or metadata["commit"] not in entry.url
        or entry.license != metadata["license"]
    ):
        raise LaneError(f"{SOURCE_LOCK}: source metadata and archive pin disagree")
    return metadata, entry


def _toolchain():
    try:
        toolchain = load_macos_toolchain(BOOTSTRAP_LOCK)
    except (BootstrapError, OSError, ValueError) as error:
        raise LaneError(f"cannot load the locked macOS toolchain: {error}") from error
    target = target_for_triple(TARGET)
    if toolchain.cpu_baseline != target.cpu_baseline_cflag:
        raise LaneError(
            "bootstrap lock CPU baseline does not match the target table: "
            f"{toolchain.cpu_baseline!r} != {target.cpu_baseline_cflag!r}"
        )
    return toolchain, target


def _supported_host() -> bool:
    return platform.system() == "Darwin" and platform.machine().lower() in {
        "arm64", "aarch64",
    }


def _require_host() -> None:
    if not _supported_host():
        raise LaneError(
            "rust-cpython currently supports only a native Apple Silicon macOS host; "
            "cross-compilation is not implemented"
        )


def _command(
    argv: list[str], *, env: dict[str, str] | None = None, timeout: int = 30
) -> dict[str, Any]:
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, env=env, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return {"argv": argv, "returncode": None, "output": str(error)}
    return {
        "argv": argv,
        "returncode": result.returncode,
        "output": (result.stdout + result.stderr).strip(),
    }


def _tool_output(argv: list[str]) -> str:
    return str(_command(argv, timeout=60)["output"])


def _rust_identity(rustup: str | None) -> dict[str, Any]:
    if rustup is None:
        return {
            "rustup": None,
            "installed": False,
            "rustc_vv": "",
            "cargo_v": "",
            "active_toolchain": "",
        }
    env = dict(os.environ)
    env["RUSTUP_TOOLCHAIN"] = RUST_CHANNEL
    env["CARGO_HOME"] = str(CARGO_HOME)
    listing = _command([rustup, "toolchain", "list"], env=env)
    installed = listing["returncode"] == 0 and any(
        line.split()[0].startswith(RUST_CHANNEL)
        for line in listing["output"].splitlines() if line.split()
    )
    if not installed:
        return {
            "rustup": rustup,
            "installed": False,
            "toolchain_list": listing["output"],
            "rustc_vv": "",
            "cargo_v": "",
            "active_toolchain": "",
        }
    return {
        "rustup": rustup,
        "installed": True,
        "toolchain_list": listing["output"],
        "rustc_vv": _command(
            [rustup, "run", RUST_CHANNEL, "rustc", "-Vv"], env=env
        )["output"],
        "cargo_v": _command(
            [rustup, "run", RUST_CHANNEL, "cargo", "-V"], env=env
        )["output"],
        "active_toolchain": _command(
            [rustup, "show", "active-toolchain"], env=env
        )["output"],
    }


def _object_path(cache_root: Path, input_: Input) -> Path:
    return Path(cache_root) / "objects" / f"{input_.sha256}.blob"


def doctor_report() -> dict[str, Any]:
    metadata, source_input = _read_lock()
    toolchain, target = _toolchain()
    rustup = shutil.which("rustup")
    rust = _rust_identity(rustup)
    source_blob = _object_path(CACHE_ROOT, source_input)
    try:
        if source_blob.is_file():
            Cache(CACHE_ROOT).require(source_input)
            source_cached = True
        else:
            source_cached = False
    except InputError:
        source_cached = False
    llvm_cache = Cache(CACHE_ROOT / "llvm")
    llvm_archive = _object_path(llvm_cache.root, toolchain.llvm_input())
    llvm_prefix_ready = (
        toolchain.llvm_prefix / ".verified.json"
    ).is_file()
    failures: list[str] = []
    if not _supported_host():
        failures.append(
            "this experiment supports only native Apple Silicon macOS "
            f"(found {platform.system()} {platform.machine()})"
        )
    failures.extend(toolchain_problems(toolchain, host_floor="26.0"))
    if rustup is None:
        failures.append("rustup is not on PATH")
    elif not rust["installed"]:
        failures.append(
            f"install the pinned compiler with `rustup toolchain install {RUST_CHANNEL} --profile minimal`"
        )
    elif not rust["rustc_vv"].startswith("rustc ") or "nightly" not in rust["rustc_vv"].splitlines()[0]:
        failures.append(f"rustup could not run the pinned compiler {RUST_CHANNEL}")
    if not rust.get("cargo_v", "").startswith("cargo ") or "nightly" not in rust["cargo_v"].splitlines()[0]:
        failures.append(f"rustup could not run the pinned Cargo for {RUST_CHANNEL}")
    if not source_cached:
        failures.append("the pinned CPython archive is not verified in .cache; run fetch")
    if not llvm_archive.is_file() or not llvm_prefix_ready:
        failures.append("the locked LLVM 23.1.2 toolchain is not provisioned; run fetch")
    if not sandbox_available():
        failures.append("/usr/bin/sandbox-exec is unavailable; the offline build cannot be sealed")
    active = rust.get("active_toolchain", "")
    if rust.get("installed") and not active.startswith(RUST_CHANNEL):
        failures.append(f"rustup did not activate {RUST_CHANNEL} for the build")

    clang = toolchain.llvm_prefix / "bin" / "clang"
    xcodebuild = _command(["xcodebuild", "-version"])
    sdk_report = _command(["xcrun", "--sdk", "macosx", "--show-sdk-version"])
    sdk_path_report = _command(["xcrun", "--sdk", "macosx", "--show-sdk-path"])
    locked_sdk_version = sdk_version(toolchain.sdkroot)
    reported_xcode_version = xcodebuild["output"].splitlines()[0] if xcodebuild["output"] else ""
    if xcodebuild["returncode"] != 0 or not reported_xcode_version.startswith(
        f"Xcode {toolchain.xcode_version}"
    ):
        failures.append(
            f"Xcode reports {reported_xcode_version or 'unavailable'}; "
            f"lock requires {toolchain.xcode_version}"
        )
    if locked_sdk_version == "unknown" or sdk_report["output"] != locked_sdk_version:
        failures.append(
            f"active macOS SDK reports {sdk_report['output'] or 'unavailable'}; "
            f"locked SDK at {toolchain.sdkroot} reports {locked_sdk_version}"
        )
    if (
        sdk_path_report["returncode"] != 0
        or not sdk_path_report["output"]
        or Path(sdk_path_report["output"]).resolve() != toolchain.sdkroot.resolve()
    ):
        failures.append(
            f"active SDK path {sdk_path_report['output'] or 'unavailable'} does not match "
            f"locked SDK path {toolchain.sdkroot}"
        )
    make_report = _command([str(toolchain.make), "--version"])
    report = {
        "host": {"os": platform.system(), "architecture": platform.machine()},
        "target": target.triple,
        "source": {
            **metadata,
            "archive_url": source_input.url,
            "archive_sha256": source_input.sha256,
            "archive_size": source_input.size,
            "cached_and_verified": source_cached,
        },
        "rust": rust,
        "cargo": {
            "private_home": str(CARGO_HOME),
            "wrapper_present": (CARGO_HOME / "bin" / "cargo").is_file(),
            "registry_cache_present": (CARGO_HOME / "registry").is_dir(),
        },
        "c_toolchain": {
            "locked_identity": toolchain.identity(),
            "clang_path": str(clang),
            "clang_version": _tool_output([str(clang), "--version"]),
            "llvm_archive_cached": llvm_archive.is_file(),
            "llvm_prefix_ready": llvm_prefix_ready,
        },
        "xcode": {
            "locked_version": toolchain.xcode_version,
            "reported_version": xcodebuild["output"],
            "sdk_path": str(toolchain.sdkroot),
            "sdk_version": locked_sdk_version,
            "active_sdk_version": sdk_report["output"],
            "active_sdk_path": sdk_path_report["output"],
        },
        "deployment_floor": toolchain.deployment_target,
        "gnu_make": {
            "path": str(toolchain.make),
            "version": make_report["output"],
        },
        "pgo_profdata": {
            "path": str(toolchain.llvm_profdata),
            "version": _tool_output([str(toolchain.llvm_profdata), "--version"]),
        },
        "network_sandbox_available": sandbox_available(),
        "problems": failures,
        "ok": not failures,
    }
    return report


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def doctor() -> int:
    try:
        report = doctor_report()
    except (LaneError, BootstrapError, OSError, ValueError) as error:
        print(json.dumps({"ok": False, "problems": [str(error)]}, indent=2))
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


def _require_nightly() -> str:
    rustup = shutil.which("rustup")
    if rustup is None:
        raise LaneError("rustup is not on PATH")
    env = dict(os.environ)
    env["RUSTUP_TOOLCHAIN"] = RUST_CHANNEL
    env["CARGO_HOME"] = str(CARGO_HOME)
    result = subprocess.run(
        [rustup, "run", RUST_CHANNEL, "rustc", "-Vv"],
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise LaneError(
            f"the pinned Rust toolchain is unavailable; install it with "
            f"`rustup toolchain install {RUST_CHANNEL} --profile minimal`"
        )
    return rustup


def _cargo_wrapper(rustup: str) -> Path:
    wrapper = CARGO_HOME / "bin" / "cargo"
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "#!/bin/sh\n"
        f"exec {shlex.quote(rustup)} run {shlex.quote(RUST_CHANNEL)} cargo \"$@\"\n"
    )
    if not wrapper.is_file() or wrapper.read_text() != content:
        wrapper.write_text(content)
    wrapper.chmod(0o755)
    return wrapper


def _source_root(extraction: Path) -> Path:
    matches = [
        child for child in extraction.iterdir()
        if child.is_dir() and (child / "configure").is_file()
    ]
    if len(matches) != 1:
        raise LaneError(
            f"expected one CPython source directory beneath {extraction}, found {len(matches)}"
        )
    source = matches[0]
    for required in ("Cargo.toml", "Cargo.lock", "Lib", "Modules", "Include/patchlevel.h"):
        if not (source / required).exists():
            raise LaneError(f"pinned source archive is missing {required}")
    metadata, _entry = _read_lock()
    found_lock_hash = hashlib.sha256((source / "Cargo.lock").read_bytes()).hexdigest()
    if found_lock_hash != metadata["cargo_lock_sha256"]:
        raise LaneError(
            "Cargo.lock digest disagrees with the source lock: "
            f"{found_lock_hash} != {metadata['cargo_lock_sha256']}"
        )
    return source


def _extract_fresh(destination: Path) -> Path:
    metadata, source_input = _read_lock()
    del metadata
    blob = Cache(CACHE_ROOT).require(source_input)
    if destination.exists():
        shutil.rmtree(destination)
    extraction = safe_extract(blob, destination)
    return _source_root(extraction)


def _source_patch_inputs() -> dict[str, Any]:
    """Validate the authored patch inputs without touching an extracted tree."""
    metadata, _entry = _read_lock()
    try:
        manifest_bytes = PATCH_MANIFEST.read_bytes()
        manifest = json.loads(manifest_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LaneError(f"cannot read source patch manifest: {error}") from error
    if not isinstance(manifest, dict) or set(manifest) != {"source_commit", "patches"}:
        raise LaneError("source patch manifest has an invalid schema")
    if manifest["source_commit"] != metadata["commit"]:
        raise LaneError("source patch manifest source commit disagrees with the source lock")
    if not isinstance(manifest["patches"], list):
        raise LaneError("source patch manifest patches must be a list")
    records: list[dict[str, str]] = []
    seen: set[str] = set()
    required = {"file", "sha256", "author", "origin", "license", "reason", "compatibility", "reproducer"}
    for entry in manifest["patches"]:
        if not isinstance(entry, dict) or set(entry) != required:
            raise LaneError("source patch manifest entry has an invalid schema")
        if any(not isinstance(entry[key], str) or not entry[key].strip() for key in required):
            raise LaneError("source patch manifest entry has an empty or invalid field")
        name = entry["file"]
        if Path(name).name != name or not name.endswith(".patch") or name in seen:
            raise LaneError(f"source patch file name is unsafe or repeated: {name!r}")
        if re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is None:
            raise LaneError(f"source patch digest is invalid: {name}")
        seen.add(name)
        patch_path = PATCH_MANIFEST.parent / name
        if patch_path.is_symlink() or not patch_path.is_file():
            raise LaneError(f"source patch is missing or is a symlink: {patch_path}")
        patch_bytes = patch_path.read_bytes()
        digest = hashlib.sha256(patch_bytes).hexdigest()
        if digest != entry["sha256"]:
            raise LaneError(f"source patch digest disagrees with manifest: {name}")
        records.append(dict(entry))
    return {
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "source_commit": metadata["commit"],
        "patches": records,
    }


def _apply_source_patches(source: Path) -> dict[str, Any]:
    """Apply authored patches only to the verified, pinned fresh source tree."""
    inputs = _source_patch_inputs()
    metadata, _entry = _read_lock()
    expected_lock = metadata["cargo_lock_sha256"]
    if hashlib.sha256((source / "Cargo.lock").read_bytes()).hexdigest() != expected_lock:
        raise LaneError("Cargo.lock digest disagrees with the source lock before patching")
    for record in inputs["patches"]:
        path = PATCH_MANIFEST.parent / record["file"]
        for check_only in (True, False):
            argv = ["git", "apply", "--whitespace=error"]
            if check_only:
                argv.append("--check")
            argv.append(str(path))
            result = subprocess.run(argv, cwd=source, capture_output=True, text=True)
            if result.returncode != 0:
                detail = (result.stderr or result.stdout).strip()
                raise LaneError(f"source patch {record['file']} does not apply: {detail}")
    if hashlib.sha256((source / "Cargo.lock").read_bytes()).hexdigest() != expected_lock:
        raise LaneError("source patches changed the pinned Cargo.lock")
    return inputs


def _llvm_ready(toolchain) -> Path:
    llvm_cache = Cache(CACHE_ROOT / "llvm")
    archive = llvm_cache.require(toolchain.llvm_input())
    attestation = llvm_cache.require(toolchain.llvm_attestation_input())
    verify_llvm_attestation_metadata(
        attestation,
        archive_filename=Path(toolchain.llvm_archive_url).name,
        archive_sha256=toolchain.llvm_archive_sha256,
        release_tag=toolchain.llvm_release_tag,
        source_commit=toolchain.llvm_source_commit,
        workflow=toolchain.llvm_workflow,
    )
    return extract_llvm_archive(
        archive,
        toolchain.llvm_prefix,
        archive_root=toolchain.llvm_archive_root,
        sha256=toolchain.llvm_archive_sha256,
        size=toolchain.llvm_archive_size,
        version=toolchain.llvm_version,
    )


def _fetch_llvm(toolchain) -> Path:
    llvm_cache = Cache(CACHE_ROOT / "llvm")
    try:
        archive = llvm_cache.fetch(toolchain.llvm_input())
        attestation = llvm_cache.fetch(toolchain.llvm_attestation_input())
        verify_llvm_attestation_metadata(
            attestation,
            archive_filename=Path(toolchain.llvm_archive_url).name,
            archive_sha256=toolchain.llvm_archive_sha256,
            release_tag=toolchain.llvm_release_tag,
            source_commit=toolchain.llvm_source_commit,
            workflow=toolchain.llvm_workflow,
        )
        return extract_llvm_archive(
            archive,
            toolchain.llvm_prefix,
            archive_root=toolchain.llvm_archive_root,
            sha256=toolchain.llvm_archive_sha256,
            size=toolchain.llvm_archive_size,
            version=toolchain.llvm_version,
        )
    except (InputError, OSError, ValueError) as error:
        raise LaneError(f"cannot provision the locked LLVM toolchain: {error}") from error


def _environment(toolchain, *, offline: bool, build_dir: Path = BUILD) -> dict[str, str]:
    rustup = shutil.which("rustup")
    rustup_directory = str(Path(rustup).parent) if rustup else "/usr/bin"
    cargo_bin = CARGO_HOME / "bin"
    llvm_bin = toolchain.llvm_prefix / "bin"
    path_parts = [
        str(cargo_bin), str(llvm_bin), rustup_directory,
        "/opt/homebrew/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin",
    ]
    path = ":".join(dict.fromkeys(path_parts))
    temp_dir = WORK / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    env = toolchain.toolchain().env()
    env.update({
        "PATH": path,
        "HOME": str(LANE / ".home"),
        "RUSTUP_HOME": os.environ.get("RUSTUP_HOME", str(Path.home() / ".rustup")),
        "CARGO_HOME": str(CARGO_HOME),
        "CARGO_NET_OFFLINE": "true" if offline else "false",
        "CARGO_TARGET_DIR": str(build_dir / "target"),
        "RUSTUP_TOOLCHAIN": RUST_CHANNEL,
        "RUST_SHARED_BUILD": "1",
        "LLVM_TARGET": TARGET,
        "BINDGEN_EXTRA_CLANG_ARGS": f"-resource-dir={toolchain.llvm_resource_dir}",
        "SOURCE_DATE_EPOCH": SOURCE_DATE_EPOCH,
        "PYTHONHASHSEED": SOURCE_DATE_EPOCH,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPYCACHEPREFIX": str(WORK / "pycache"),
        "TMPDIR": str(temp_dir),
        "PKG_CONFIG": str(toolchain.pkgconf),
    })
    return env


def _test_environment(toolchain) -> dict[str, str]:
    """Let CPython's test runner populate its isolated bytecode cache."""
    env = _environment(toolchain, offline=True)
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    return env


def _run_logged(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log: Path,
    sealed: SealedRun | None = None,
) -> subprocess.CompletedProcess:
    log.parent.mkdir(parents=True, exist_ok=True)
    print(f"RUN   {' '.join(shlex.quote(part) for part in argv)}")
    print(f"LOG   {log}")
    if sealed is not None:
        return sealed.run(argv, cwd=cwd, env=env, log=log)
    with log.open("w") as output:
        return subprocess.run(
            argv, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT
        )


def _require_command(
    argv: list[str], *, cwd: Path, env: dict[str, str], log: Path,
    sealed: SealedRun | None = None,
) -> subprocess.CompletedProcess:
    result = _run_logged(argv, cwd=cwd, env=env, log=log, sealed=sealed)
    if result.returncode != 0:
        raise LaneError(
            f"command failed with exit status {result.returncode}; "
            f"inspect {log}"
        )
    return result


def _fetch_cargo_dependencies(source: Path, toolchain) -> None:
    env = _environment(toolchain, offline=False)
    env["PATH"] = f"{CARGO_HOME / 'bin'}:{env['PATH']}"
    command = [
        str(CARGO_HOME / "bin" / "cargo"), "fetch", "--locked",
        "--manifest-path", str(source / "Cargo.toml"),
    ]
    cargo_lock = source / "Cargo.lock"
    before = hashlib.sha256(cargo_lock.read_bytes()).hexdigest()
    _require_command(
        command, cwd=source, env=env, log=LOGS / "cargo-fetch.log"
    )
    after = hashlib.sha256(cargo_lock.read_bytes()).hexdigest()
    metadata, _entry = _read_lock()
    if before != metadata["cargo_lock_sha256"] or after != before:
        raise LaneError("cargo fetch changed the locked Cargo.lock")


def _zlib_input() -> tuple[dict[str, str], Input]:
    """Use the proof's existing source pin for the optional whole-build candidate."""
    try:
        metadata = json.loads(ZLIB_LOCK.read_text())["backend"]
        entries = load_lock(ZLIB_LOCK)
    except (OSError, ValueError, KeyError, TypeError, InputError) as error:
        raise LaneError(f"cannot read pinned zlib-rs backend: {error}") from error
    expected = {
        "repository": "https://github.com/trifectatechfoundation/zlib-rs",
        "crate": "libz-rs-sys-cdylib",
        "version": "0.6.7",
        "license": "Zlib",
    }
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise LaneError("zlib-rs metadata disagrees with the proven 0.6.7 pin")
    if len(entries) != 1:
        raise LaneError("zlib-rs lock must contain exactly one source archive")
    entry = entries[0]
    if (entry.name != metadata["crate"] or entry.version != metadata["version"]
            or entry.role != "build-source" or entry.target != TARGET
            or entry.license != metadata["license"]
            or entry.url != "https://static.crates.io/crates/libz-rs-sys-cdylib/libz-rs-sys-cdylib-0.6.7.crate"):
        raise LaneError("zlib-rs archive entry disagrees with backend metadata")
    cargo_hash = metadata.get("cargo_lock_sha256")
    if not isinstance(cargo_hash, str) or re.fullmatch(r"[0-9a-f]{64}", cargo_hash) is None:
        raise LaneError("zlib-rs Cargo.lock pin is invalid")
    return metadata, entry


def _zlib_source(blob: Path) -> Path:
    if ZLIB_SOURCE.exists():
        shutil.rmtree(ZLIB_SOURCE)
    extraction = safe_extract(blob, ZLIB_SOURCE)
    roots = [path for path in extraction.iterdir() if path.is_dir()]
    if len(roots) != 1:
        raise LaneError("zlib-rs archive must contain exactly one crate root")
    source = roots[0]
    manifest = source / "Cargo.toml"
    cargo_lock = source / "Cargo.lock"
    if not manifest.is_file() or not cargo_lock.is_file():
        raise LaneError("zlib-rs archive lacks Cargo.toml or Cargo.lock")
    metadata, _entry = _zlib_input()
    try:
        manifest_data = tomllib.loads(manifest.read_text())
        package = manifest_data["package"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise LaneError(f"cannot read pinned zlib-rs Cargo.toml: {error}") from error
    if any(package.get(key) != metadata[value] for key, value in
           (("name", "crate"), ("version", "version"), ("license", "license"))):
        raise LaneError("zlib-rs Cargo.toml disagrees with the source pin")
    if "staticlib" not in manifest_data.get("lib", {}).get("crate-type", []):
        raise LaneError("zlib-rs crate does not declare a static library")
    if hashlib.sha256(cargo_lock.read_bytes()).hexdigest() != metadata["cargo_lock_sha256"]:
        raise LaneError("zlib-rs Cargo.lock digest disagrees with the source pin")
    return source


def _zlib_cargo_env(toolchain, *, offline: bool) -> dict[str, str]:
    env = _environment(toolchain, offline=offline)
    env["CARGO_TARGET_DIR"] = str(ZLIB_TARGET)
    for key in ("RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER"):
        env.pop(key, None)
    return env


def _fetch_zlib(toolchain) -> None:
    _metadata, entry = _zlib_input()
    blob = Cache(CACHE_ROOT).fetch(entry)
    source = _zlib_source(blob)
    _require_command(
        [str(CARGO_HOME / "bin" / "cargo"), "fetch", "--locked",
         "--manifest-path", str(source / "Cargo.toml")],
        cwd=source, env=_zlib_cargo_env(toolchain, offline=False),
        log=LOGS / "zlib-candidate-fetch.log",
    )
    if hashlib.sha256((source / "Cargo.lock").read_bytes()).hexdigest() != _zlib_input()[0]["cargo_lock_sha256"]:
        raise LaneError("zlib-rs Cargo.lock changed during fetch")


def _build_zlib(toolchain, sandbox: SealedRun) -> dict[str, Any]:
    metadata, entry = _zlib_input()
    blob = Cache(CACHE_ROOT).require(entry)
    source = _zlib_source(blob)
    _require_command(
        [str(CARGO_HOME / "bin" / "cargo"), "build", "--release", "--locked",
         "--offline", "--manifest-path", str(source / "Cargo.toml")],
        cwd=source, env=sandbox.environment(_zlib_cargo_env(toolchain, offline=True)),
        log=LOGS / "zlib-candidate-build.log",
        sealed=sandbox,
    )
    if hashlib.sha256((source / "Cargo.lock").read_bytes()).hexdigest() != metadata["cargo_lock_sha256"]:
        raise LaneError("zlib-rs Cargo.lock changed during build")
    if not ZLIB_ARCHIVE.is_file():
        raise LaneError(f"zlib-rs did not produce {ZLIB_ARCHIVE}")
    return {
        "source_lock": str(ZLIB_LOCK),
        "source_lock_sha256": hashlib.sha256(ZLIB_LOCK.read_bytes()).hexdigest(),
        "repository": metadata["repository"],
        "crate": metadata["crate"],
        "version": metadata["version"],
        "source_archive_sha256": entry.sha256,
        "source_archive_size": entry.size,
        "cargo_lock_sha256": metadata["cargo_lock_sha256"],
        "static_library": str(ZLIB_ARCHIVE),
        "static_library_sha256": hashlib.sha256(ZLIB_ARCHIVE.read_bytes()).hexdigest(),
        "static_library_size": ZLIB_ARCHIVE.stat().st_size,
        "cargo_build_log": str(LOGS / "zlib-candidate-build.log"),
    }


def fetch(*, zlib_rs: bool = False) -> int:
    _require_host()
    rustup = _require_nightly()
    _cargo_wrapper(rustup)
    metadata, source_input = _read_lock()
    toolchain, _target = _toolchain()
    try:
        source_blob = Cache(CACHE_ROOT).fetch(source_input)
    except (InputError, OSError) as error:
        raise LaneError(f"cannot fetch the pinned CPython source: {error}") from error
    print(f"OK    source archive -> {source_blob}")
    _fetch_llvm(toolchain)
    print(f"OK    LLVM {toolchain.llvm_version} -> {toolchain.llvm_prefix}")
    WORK.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cargo-fetch-", dir=WORK) as temporary:
        source = _source_root(safe_extract(source_blob, Path(temporary) / "source"))
        _fetch_cargo_dependencies(source, toolchain)
    if zlib_rs:
        _fetch_zlib(toolchain)
    print(
        f"OK    Cargo dependencies cached under {CARGO_HOME}; "
        f"source pin {metadata['commit']}"
    )
    return 0


def _profile_task(jobs: int) -> str:
    if jobs < 1:
        raise ValueError("profile task requires at least one worker")
    return f"{PROFILE_TASK} -j {jobs}"


def _test_jobs() -> int:
    return max(1, min(4, (os.cpu_count() or 4) - 1))


def _brew_pkg_config_path() -> str:
    brew = shutil.which("brew")
    if not brew:
        return ""
    found: list[str] = []
    for formula in ("openssl@3", "sqlite", "libffi", "xz", "bzip2", "zstd"):
        result = _command([brew, "--prefix", formula])
        if result["returncode"] != 0:
            continue
        pkgconfig = Path(result["output"]) / "lib" / "pkgconfig"
        if pkgconfig.is_dir():
            found.append(str(pkgconfig))
    return ":".join(dict.fromkeys(found))


def _configuration(toolchain, target, jobs: int, *, zlib_archive: Path | None = None) -> tuple[list[str], dict[str, str]]:
    profile_task = _profile_task(jobs)
    flags = " ".join((
        "-O3", target.cpu_baseline_cflag, "-fPIC",
        f"-mmacosx-version-min={toolchain.deployment_target}",
    ))
    link_flags = f"-mmacosx-version-min={toolchain.deployment_target}"
    args = [
        f"--prefix={STAGE}",
        "--enable-shared",
        "--with-lto=thin",
        "--enable-optimizations",
        "--enable-experimental-jit=no",
        "--with-tail-call-interp=no",
        "--without-ensurepip",
    ]
    env = _environment(toolchain, offline=True)
    env.update({
        "CFLAGS": flags,
        "CXXFLAGS": flags,
        "CPPFLAGS": f"-isysroot {toolchain.sdkroot}",
        "PY_CPPFLAGS": f"-isysroot {toolchain.sdkroot}",
        "LDFLAGS": link_flags,
        "PROFILE_TASK": profile_task,
        "LLVM_PROFDATA": str(toolchain.llvm_profdata),
        "PKG_CONFIG_PATH": _brew_pkg_config_path(),
    })
    if zlib_archive is not None:
        env["ZLIB_LIBS"] = str(zlib_archive)
    return args, env


def _macos_sandbox() -> SealedRun:
    if not sandbox_available():
        raise LaneError("offline build requires /usr/bin/sandbox-exec")
    sandbox = SealedRun(write_paths=[LANE], home=LANE / ".home")
    try:
        proof = network_boundary_selftest(Path(sys.executable), WORK / "sandbox-probe")
    except (SandboxError, OSError, subprocess.SubprocessError) as error:
        raise LaneError(f"cannot prove the offline network boundary: {error}") from error
    if not proof.get("ok"):
        raise LaneError(f"sandbox network-denial self-test failed: {proof}")
    return sandbox


def _make_value(makefile: Path, name: str) -> str:
    prefix = f"{name}="
    for line in makefile.read_text(errors="replace").splitlines():
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return ""


def _build_python() -> Path:
    makefile = BUILD / "Makefile"
    if not makefile.is_file():
        raise LaneError(f"configured build Makefile is missing: {makefile}")
    name = _make_value(makefile, "BUILDPYTHON")
    suffix = _make_value(makefile, "BUILDEXE")
    name = name.replace("$(BUILDEXE)", suffix)
    if not name or "$" in name or Path(name).name != name:
        raise LaneError(f"cannot resolve CPython build interpreter name {name!r}")
    return BUILD / name


def _module_report(install: Path, python: Path, toolchain) -> dict[str, Any]:
    code = r'''
import base64, binascii, json, sys, sysconfig, _base64
vectors = [b"", b"f", b"fo", b"foo", bytes(range(256)), b"rust-cpython" * 4096]
for value in vectors:
    actual = _base64.standard_b64encode(value)
    expected = binascii.b2a_base64(value, newline=False)
    if actual != expected or actual != base64.b64encode(value):
        raise SystemExit("_base64 disagrees with the CPython base64/binascii result")
for value in (bytearray(b"buffer"), memoryview(b"view")):
    if _base64.standard_b64encode(value) != binascii.b2a_base64(value, newline=False):
        raise SystemExit("_base64 buffer-protocol result differs from binascii")
if sys.implementation.name != "cpython" or sys.version_info[:2] != (3, 16):
    raise SystemExit("interpreter is not CPython 3.16")
if sysconfig.get_config_var("Py_GIL_DISABLED") in (1, "1"):
    raise SystemExit("the experimental build unexpectedly disabled the GIL")
if hasattr(sys, "_is_gil_enabled") and not sys._is_gil_enabled():
    raise SystemExit("the interpreter reports that the GIL is disabled")
print(json.dumps({
    "implementation": sys.implementation.name,
    "version": sys.version,
    "gil_disabled": sysconfig.get_config_var("Py_GIL_DISABLED"),
    "gil_enabled": sys._is_gil_enabled() if hasattr(sys, "_is_gil_enabled") else True,
    "extension_suffix": sysconfig.get_config_var("EXT_SUFFIX"),
    "config_args": sysconfig.get_config_var("CONFIG_ARGS"),
    "cflags": sysconfig.get_config_var("CFLAGS"),
    "ldflags": sysconfig.get_config_var("LDFLAGS"),
    "base64_vectors": len(vectors) + 2,
    "base64_matches_binascii": True,
}))
'''
    env = _environment(toolchain, offline=True)
    result = subprocess.run(
        [str(python), "-I", "-S", "-c", code],
        cwd=install,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise LaneError(
            "installed interpreter/_base64 smoke test failed: "
            f"{(result.stderr or result.stdout).strip()[-1000:]}"
        )
    try:
        interpreter = json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise LaneError(f"cannot parse installed interpreter report: {result.stdout!r}") from error
    suffix = interpreter["extension_suffix"]
    module_path = Path(subprocess.run(
        [str(python), "-I", "-S", "-c", "import _base64; print(_base64.__file__)"],
        cwd=install, env=env, capture_output=True, text=True, timeout=30, check=True,
    ).stdout.strip()).resolve()
    if not module_path.name.endswith(suffix):
        raise LaneError(f"Rust module {module_path.name} does not use {suffix}")
    try:
        module_path.relative_to(install.resolve())
    except ValueError as error:
        raise LaneError(f"Rust module was loaded outside the stage tree: {module_path}") from error

    header = macho.read_header(module_path)
    version = macho.build_version(module_path)
    if header.arch != "arm64":
        raise LaneError(f"Rust module architecture is {header.arch}, expected arm64")
    if version is None or version.minos != toolchain.deployment_target:
        raise LaneError(
            f"Rust module deployment floor is {version.minos if version else None}, "
            f"expected {toolchain.deployment_target}"
        )
    dependencies = macho.dependencies(module_path)
    rpaths = macho.rpaths(module_path)
    forbidden_markers = (
        "/opt/homebrew", ".rustup", ".cargo-home", "/.cache/llvm/",
    )
    unexpected = [
        item for item in [*dependencies, *rpaths]
        if any(marker in item for marker in forbidden_markers)
    ]
    if unexpected:
        raise LaneError(
            "Rust module has a build-tool/Homebrew dependency or rpath: "
            + ", ".join(unexpected)
        )
    nm = toolchain.llvm_prefix / "bin" / "llvm-nm"
    symbols = _command([str(nm), "-g", str(module_path)])
    if symbols["returncode"] != 0:
        raise LaneError(f"cannot inspect Rust module exports: {symbols['output']}")
    exports = []
    for line in symbols["output"].splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[-1].lstrip("_") == "PyInit__base64":
            exports.append(fields[-1])
    if not exports:
        raise LaneError("Rust module does not export PyInit__base64")
    interpreter["module_path"] = str(module_path)
    interpreter["module_dependencies"] = dependencies
    interpreter["module_rpaths"] = rpaths
    interpreter["module_exports"] = exports
    interpreter["module_arch"] = header.arch
    interpreter["module_minos"] = version.minos
    return interpreter


def _zlib_module_report(python: Path, toolchain) -> dict[str, Any]:
    """Prove the installed whole-build module uses the candidate C ABI."""
    code = (
        "import json,zlib; "
        "payload=bytes(range(256))*4096; "
        "assert zlib.decompress(zlib.compress(payload))==payload; "
        "print(json.dumps({'path':zlib.__file__,"
        "'header_version':zlib.ZLIB_VERSION,"
        "'runtime_version':zlib.ZLIB_RUNTIME_VERSION}))"
    )
    result = subprocess.run(
        [str(python), "-I", "-S", "-c", code],
        cwd=STAGE, env=_environment(toolchain, offline=True),
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise LaneError(f"installed zlib candidate smoke failed: {result.stderr.strip()}")
    try:
        identity = json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise LaneError("installed zlib candidate did not report its identity") from error
    if identity["runtime_version"] != "1.3.0-zlib-rs-0.6.7":
        raise LaneError(f"installed zlib runtime is not the pinned backend: {identity['runtime_version']!r}")
    module = Path(identity["path"]).resolve()
    try:
        module.relative_to(STAGE.resolve())
    except ValueError as error:
        raise LaneError(f"zlib module was loaded outside the stage tree: {module}") from error
    if not module.is_file():
        raise LaneError(f"installed zlib module is missing: {module}")
    dependencies = macho.dependencies(module)
    if any("libz" in dependency.lower() for dependency in dependencies):
        raise LaneError("installed zlib module retains a dynamic libz dependency")
    symbols = _command([
        str(toolchain.llvm_prefix / "bin" / "llvm-nm"),
        "-g", "--defined-only", str(module),
    ])
    if symbols["returncode"] != 0:
        raise LaneError(f"cannot inspect installed zlib module symbols: {symbols['output']}")
    for symbol in ("_zlibVersion", "_deflateInit2_", "_inflateInit2_"):
        if symbol not in symbols["output"]:
            raise LaneError(f"installed zlib module lacks static backend symbol {symbol}")
    return {
        **identity,
        "path": str(module),
        "sha256": hashlib.sha256(module.read_bytes()).hexdigest(),
        "dynamic_dependencies": dependencies,
        "static_backend_symbols": ["zlibVersion", "deflateInit2_", "inflateInit2_"],
        "python_wrapper": "unchanged pinned CPython Modules/zlibmodule.c",
    }


def _workspace_members(source: Path, env: dict[str, str]) -> list[str]:
    command = [
        str(CARGO_HOME / "bin" / "cargo"), "metadata", "--locked", "--offline",
        "--no-deps", "--format-version", "1", "--manifest-path",
        str(source / "Cargo.toml"),
    ]
    result = subprocess.run(
        command, cwd=source, env=env, capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise LaneError(f"cargo metadata failed: {(result.stderr or result.stdout).strip()}")
    document = json.loads(result.stdout)
    names = {package["id"]: package["name"] for package in document["packages"]}
    return sorted(names[member] for member in document["workspace_members"] if member in names)


def _built_workspace_members(source: Path, env: dict[str, str]) -> list[str]:
    members = set(_workspace_members(source, env))
    pattern = re.compile(r"(?:Compiling|Fresh) ([^ ]+) v[^ ]+")
    found: set[str] = set()
    for log in sorted(LOGS.glob("cpython-*.log")):
        for line in log.read_text(errors="replace").splitlines():
            match = pattern.search(line)
            if match and match.group(1) in members:
                found.add(match.group(1))
    return sorted(found)


def _configure_source(source: Path, toolchain, target, jobs: int, sandbox: SealedRun, patches: dict[str, Any], zlib_backend: dict[str, Any] | None = None) -> dict[str, Any]:
    rustup = _require_nightly()
    _cargo_wrapper(rustup)
    if BUILD.exists():
        shutil.rmtree(BUILD)
    if STAGE.exists():
        shutil.rmtree(STAGE)
    BUILD.mkdir(parents=True)
    STAGE.mkdir(parents=True)
    args, env = _configuration(
        toolchain, target, jobs,
        zlib_archive=ZLIB_ARCHIVE if zlib_backend is not None else None,
    )
    env.update({
        "PY_CC": str(toolchain.llvm_prefix / "bin" / "clang"),
        "PY_CPPFLAGS": env["CPPFLAGS"],
        "PY_CFLAGS": env["CFLAGS"],
        "PYTHON_BUILD_DIR": str(BUILD),
        "CARGO_TARGET_AARCH64_APPLE_DARWIN_LINKER": str(toolchain.llvm_prefix / "bin" / "clang"),
        "IPHONEOS_DEPLOYMENT_TARGET": "",
    })
    env = sandbox.environment(env)
    source_date_env = dict(env)
    configure = [str(source / "configure"), *args]
    _require_command(
        configure, cwd=BUILD, env=source_date_env,
        log=LOGS / "cpython-configure.log", sealed=sandbox,
    )
    if zlib_backend is not None:
        configured_zlib = _make_value(BUILD / "Makefile", "ZLIB_LIBS")
        if configured_zlib != str(ZLIB_ARCHIVE):
            raise LaneError(f"configure did not preserve the pinned zlib archive: {configured_zlib!r}")
    make = [str(toolchain.make), f"-j{jobs}"]
    _require_command(
        make, cwd=BUILD, env=source_date_env,
        log=LOGS / "cpython-build.log", sealed=sandbox,
    )
    _require_command(
        [str(toolchain.make), "install"], cwd=BUILD, env=source_date_env,
        log=LOGS / "cpython-install.log", sealed=sandbox,
    )
    python = STAGE / "bin" / "python3.16"
    if not python.is_file():
        raise LaneError(f"CPython install did not produce {python}")
    module = _module_report(STAGE, python, toolchain)
    if zlib_backend is not None:
        zlib_backend["installed_module"] = _zlib_module_report(python, toolchain)
    cargo_env = dict(source_date_env)
    cargo_env.update({
        "PYTHON_BUILD_DIR": str(BUILD),
        "PY_CC": str(toolchain.llvm_prefix / "bin" / "clang"),
        "PY_CPPFLAGS": source_date_env["CPPFLAGS"],
        "PY_CFLAGS": source_date_env["CFLAGS"],
        "CARGO_TARGET_DIR": str(BUILD / "target"),
        "LLVM_TARGET": TARGET,
        "RUST_SHARED_BUILD": "1",
        "CARGO_TARGET_AARCH64_APPLE_DARWIN_LINKER": str(toolchain.llvm_prefix / "bin" / "clang"),
    })
    cargo_lock_hash = hashlib.sha256((source / "Cargo.lock").read_bytes()).hexdigest()
    metadata, source_input = _read_lock()
    source_hash = Cache(CACHE_ROOT).require(source_input)
    makefile = BUILD / "Makefile"
    cargo_profile = _make_value(makefile, "CARGO_PROFILE")
    if cargo_profile != "release":
        raise LaneError(
            f"optimized CPython configured Cargo profile {cargo_profile!r}; expected 'release'"
        )
    workspace_members = _workspace_members(source, cargo_env)
    built_workspace_members = _built_workspace_members(source, cargo_env)
    required_rust_members = {"_base64", "cpython-sys"}
    missing_rust_members = sorted(required_rust_members - set(built_workspace_members))
    if missing_rust_members:
        raise LaneError(
            "CPython build did not compile required Rust workspace members: "
            + ", ".join(missing_rust_members)
        )
    report = {
        "status": "built",
        "source": {
            "repository": metadata["repository"],
            "branch": metadata["branch"],
            "commit": metadata["commit"],
            "version": metadata["version"],
            "archive_sha256": source_input.sha256,
            "archive_size": source_input.size,
            "cargo_lock_sha256": cargo_lock_hash,
            "source_archive_path": str(source_hash),
            "patches": patches,
        },
        "interpreter": module,
        "build_interpreter": str(_build_python()),
        "rust": _rust_identity(rustup),
        "c_toolchain": toolchain.identity(),
        "sdk": {
            "path": str(toolchain.sdkroot),
            "version": sdk_version(toolchain.sdkroot),
            "xcode_version": toolchain.xcode_version,
        },
        "configure_arguments": configure,
        "configure_environment": {
            key: env.get(key, "")
            for key in (
                "CC", "CXX", "AR", "RANLIB", "CFLAGS", "CXXFLAGS", "LDFLAGS",
                "CPPFLAGS", "PY_CPPFLAGS", "SDKROOT", "MACOSX_DEPLOYMENT_TARGET", "LLVM_PROFDATA",
                "PROFILE_TASK", "BINDGEN_EXTRA_CLANG_ARGS", "SOURCE_DATE_EPOCH", "PYTHONHASHSEED",
                "PKG_CONFIG", "PKG_CONFIG_PATH", "ZLIB_LIBS",
            )
        },
        "pgo_task": env["PROFILE_TASK"],
        "lto_mode": "thin",
        "cargo_profile": cargo_profile,
        "cargo_home": str(CARGO_HOME),
        "cargo_target_dir": str(BUILD / "target"),
        "cargo_workspace_members": workspace_members,
        "built_rust_workspace_members": built_workspace_members,
        "zlib_backend": zlib_backend if zlib_backend is not None else {"kind": "platform"},
        "offline_boundary": {
            "mechanism": "sandbox-exec with deny network*",
            "network_self_test": "passed",
            "cargo_net_offline": env["CARGO_NET_OFFLINE"],
        },
        "logs": {
            "configure": str(LOGS / "cpython-configure.log"),
            "build": str(LOGS / "cpython-build.log"),
            "install": str(LOGS / "cpython-install.log"),
        },
        "tests": {},
    }
    _write_json(BUILD_REPORT, report)
    return report


def build(*, zlib_rs: bool = False) -> int:
    _require_host()
    doctor = doctor_report()
    if not doctor["ok"]:
        raise LaneError("doctor found prerequisites missing; run doctor for details")
    rustup = _require_nightly()
    _cargo_wrapper(rustup)
    toolchain, target = _toolchain()
    _llvm_ready(toolchain)
    sandbox = _macos_sandbox() if zlib_rs else None
    zlib_backend = _build_zlib(toolchain, sandbox) if sandbox is not None else None
    source = _extract_fresh(SOURCE)
    wrapper = source / "Modules" / "zlibmodule.c"
    wrapper_sha256 = hashlib.sha256(wrapper.read_bytes()).hexdigest() if zlib_rs else None
    patches = _apply_source_patches(source)
    if zlib_backend is not None:
        if hashlib.sha256(wrapper.read_bytes()).hexdigest() != wrapper_sha256:
            raise LaneError("candidate patches changed pinned Modules/zlibmodule.c")
        zlib_backend["cpython_zlibmodule_sha256"] = wrapper_sha256
    env = _environment(toolchain, offline=True)
    _require_command(
        [str(CARGO_HOME / "bin" / "cargo"), "fetch", "--locked", "--offline",
         "--manifest-path", str(source / "Cargo.toml")],
        cwd=source, env=env, log=LOGS / "cargo-offline-check.log",
    )
    if sandbox is None:
        sandbox = _macos_sandbox()
    jobs = max(1, (os.cpu_count() or 4) - 1)
    report = _configure_source(source, toolchain, target, jobs, sandbox, patches, zlib_backend)
    print(f"OK    CPython {report['interpreter']['version'].split()[0]} -> {STAGE}")
    print(f"OK    Rust _base64 -> {report['interpreter']['module_path']}")
    _write_json(BUILD_REPORT, report)
    return 0


def _test_record(returncode: int, log: Path, summary: str = "") -> dict[str, Any]:
    return {
        "status": "passed" if returncode == 0 else "failed",
        "returncode": returncode,
        "log": str(log),
        "summary": summary,
    }


def _run_python_test(
    argv: list[str], *, cwd: Path, env: dict[str, str], log: Path
) -> dict[str, Any]:
    result = _run_logged(argv, cwd=cwd, env=env, log=log)
    output = log.read_text(errors="replace")
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    summary = " | ".join(lines[-5:])
    return _test_record(result.returncode, log, summary)


def test() -> int:
    _require_host()
    if not BUILD_REPORT.is_file() or not _build_python().is_file():
        raise LaneError("no completed Rust-for-CPython build; run build first")
    report = json.loads(BUILD_REPORT.read_text())
    if report.get("status") not in {"built", "tests-failed", "complete"}:
        raise LaneError("build report does not describe a completed build; run build first")
    patches = _source_patch_inputs()
    if report["source"].get("patches") != patches:
        raise LaneError("current source patches disagree with the completed build report")
    source = SOURCE
    if not (source / "Cargo.toml").is_file():
        source = _extract_fresh(SOURCE)
        _apply_source_patches(source)
    toolchain, _target = _toolchain()
    rustup = _require_nightly()
    _cargo_wrapper(rustup)
    env = _test_environment(toolchain)
    env.update({
        "PYTHON_BUILD_DIR": str(BUILD),
        "PY_CC": str(toolchain.llvm_prefix / "bin" / "clang"),
        "PY_CPPFLAGS": f"-isysroot {toolchain.sdkroot}",
        "PY_CFLAGS": env.get("CFLAGS", ""),
        "CARGO_TARGET_DIR": str(BUILD / "target"),
        "LLVM_TARGET": TARGET,
        "RUST_SHARED_BUILD": "1",
        "CARGO_TARGET_AARCH64_APPLE_DARWIN_LINKER": str(toolchain.llvm_prefix / "bin" / "clang"),
    })
    build_python = _build_python()
    report["build_interpreter"] = str(build_python)
    results: dict[str, Any] = {}
    _write_json(BUILD_REPORT, report)
    cargo = _run_python_test(
        [str(CARGO_HOME / "bin" / "cargo"), "test", "--locked", "--offline", "--workspace", "--manifest-path", str(source / "Cargo.toml")],
        cwd=source, env=env, log=LOGS / "cargo-test.log",
    )
    results["cargo_workspace"] = cargo
    report["tests"] = results
    _write_json(BUILD_REPORT, report)
    if cargo["returncode"] != 0:
        raise LaneError(f"Cargo workspace tests failed; inspect {cargo['log']}")

    targeted = _run_python_test(
        [str(build_python), "-m", "test", "-j", str(_test_jobs()),
         "test_base64", "test_binascii", "test_import", "test_importlib",
         "test_sysconfig", "test_capi", "test_embed"],
        cwd=BUILD, env=env, log=LOGS / "cpython-targeted-tests.log",
    )
    results["targeted_cpython"] = targeted
    report["tests"] = results
    _write_json(BUILD_REPORT, report)
    if targeted["returncode"] != 0:
        raise LaneError(f"targeted CPython tests failed; inspect {targeted['log']}")

    regression = _run_python_test(
        [str(build_python), "-m", "test", "-j", str(_test_jobs())],
        cwd=BUILD, env=env, log=LOGS / "cpython-regression-tests.log",
    )
    results["cpython_regression"] = regression
    report["tests"] = results
    report["status"] = "complete" if regression["returncode"] == 0 else "tests-failed"
    _write_json(BUILD_REPORT, report)
    if regression["returncode"] != 0:
        raise LaneError(f"CPython regression suite failed; inspect {regression['log']}")
    print("OK    Cargo workspace, targeted CPython tests, and broad regression suite")
    return 0


def clean() -> int:
    for path in (WORK, STAGE, LOGS, RESULTS, LANE / ".home"):
        if path.exists():
            shutil.rmtree(path)
    print(f"OK    removed work, stage, logs, and results; kept private Cargo registry at {CARGO_HOME}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Isolated Rust-for-CPython 3.16 experiment")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("doctor", "report host, source, and toolchain readiness"),
        ("fetch", "fetch locked sources and Cargo dependencies"),
        ("build", "build and validate the native arm64 interpreter offline"),
        ("test", "run Rust and CPython tests"),
        ("clean", "remove build outputs while keeping the private Cargo cache"),
    ):
        command_parser = subparsers.add_parser(name, help=help_text)
        if name in ("fetch", "build"):
            command_parser.add_argument(
                "--zlib-rs", action="store_true",
                help="include pinned zlib-rs 0.6.7 in this optional candidate build",
            )
    args = parser.parse_args(argv)
    commands = {"doctor": doctor, "fetch": fetch, "build": build, "test": test, "clean": clean}
    try:
        if args.command in ("fetch", "build"):
            return commands[args.command](zlib_rs=args.zlib_rs)
        return commands[args.command]()
    except (LaneError, InputError, BootstrapError, SandboxError, OSError, ValueError) as error:
        print(f"FAIL  {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
