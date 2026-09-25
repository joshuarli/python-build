#!/usr/bin/env python3
"""Build and validate the isolated Rust-for-CPython lane.

The lane runs natively on Apple Silicon macOS (`aarch64-apple-darwin`) or on
x86_64 glibc Linux (`x86_64-unknown-linux-gnu`); the host selects the target.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any, NamedTuple

REPO = Path(__file__).resolve().parents[1]
LANE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(LANE))

import lane_linux  # noqa: E402
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
    LINUX_X86_64_LAYOUT,
    MACOS_AARCH64_LAYOUT,
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

MACOS_TARGET = "aarch64-apple-darwin"
LINUX_TARGET = lane_linux.TARGET
# Source archives are platform independent. Locks written before the Linux
# lane name the macOS target; either lane target is accepted for them.
LANE_TARGETS = frozenset({MACOS_TARGET, LINUX_TARGET})
TARGET = LINUX_TARGET if lane_linux.supported_host() else MACOS_TARGET
IS_LINUX = TARGET == LINUX_TARGET
# Mach-O prefixes C symbol names with an underscore; ELF does not.
SYMBOL_PREFIX = "" if IS_LINUX else "_"
PLATFORM_LIBZ = "libz.so.1" if IS_LINUX else "/usr/lib/libz.1.dylib"
# zlib.ZLIB_RUNTIME_VERSION reported by the platform library each lane links.
PLATFORM_ZLIB_VERSION = "1.3" if IS_LINUX else "1.2.12"
RUST_CHANNEL = "nightly-2026-09-15"
SOURCE_LOCK = LANE / "sources.lock.json"
PATCH_MANIFEST = LANE / "patches" / "manifest.json"
ZLIB_LOCK = LANE / "zlib-proof" / "sources.lock.json"
BOOTSTRAP_LOCK = REPO / "bootstrap.lock.json"
LINUX_TOOLCHAIN_LOCK = LANE / "linux-toolchain.lock.json"
CACHE_ROOT = REPO / ".cache"
CARGO_HOME = LANE / ".cargo-home"
WORK = LANE / "work"
ZLIB_SOURCE = WORK / "zlib-candidate-source"
ZLIB_TARGET = WORK / "zlib-candidate-target"
ZLIB_ARCHIVE = ZLIB_TARGET / "release" / "libz_rs.a"
ZLIB_HYBRID_PREFIX = "python_build_rs_"
BUILD = WORK / "build"
SOURCE = WORK / "source"
STAGE = LANE / "stage"
LOGS = LANE / "logs"
RESULTS = LANE / "results"
BUILD_REPORT = RESULTS / "build.json"
VARIANT = ""
_VARIANT_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")


def _select_variant(name: str) -> None:
    """Direct build outputs to a named variant beside the default candidate.

    Each variant has its own source, build, stage, logs and report, so
    controls such as the unpatched fork or the zlib candidate cannot
    overwrite the default `stage/`. The empty name keeps the default paths.
    """
    global VARIANT, SOURCE, BUILD, STAGE, LOGS, BUILD_REPORT
    global ZLIB_SOURCE, ZLIB_TARGET, ZLIB_ARCHIVE
    if not name:
        return
    if _VARIANT_NAME.fullmatch(name) is None or name in {"no-rust"}:
        raise LaneError(f"invalid build variant name {name!r}")
    VARIANT = name
    root = WORK / "variants" / name
    SOURCE = root / "source"
    BUILD = root / "build"
    ZLIB_SOURCE = root / "zlib-candidate-source"
    ZLIB_TARGET = root / "zlib-candidate-target"
    ZLIB_ARCHIVE = ZLIB_TARGET / "release" / "libz_rs.a"
    STAGE = LANE / f"stage-{name}"
    LOGS = LANE / "logs" / "variants" / name
    BUILD_REPORT = RESULTS / f"build-{name}.json"
SOURCE_DATE_EPOCH = "1704067200"
PROFILE_TASK = "-m test --pgo"


class LaneError(Exception):
    """The pinned experimental build lane cannot safely continue."""


class LaneTarget(NamedTuple):
    """The Linux lane's target; the production target table stays unchanged."""

    triple: str
    cpu_baseline_cflag: str


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
        or entry.target not in LANE_TARGETS
        or metadata["commit"] not in entry.url
        or entry.license != metadata["license"]
    ):
        raise LaneError(f"{SOURCE_LOCK}: source metadata and archive pin disagree")
    return metadata, entry


def _toolchain():
    if IS_LINUX:
        try:
            toolchain = lane_linux.load_linux_toolchain(LINUX_TOOLCHAIN_LOCK, CACHE_ROOT)
        except lane_linux.LinuxHostError as error:
            raise LaneError(str(error)) from error
        return toolchain, LaneTarget(LINUX_TARGET, toolchain.cpu_baseline)
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
    if IS_LINUX:
        return True
    return platform.system() == "Darwin" and platform.machine().lower() in {
        "arm64", "aarch64",
    }


def _require_host() -> None:
    if not _supported_host():
        raise LaneError(
            "rust-cpython supports only native Apple Silicon macOS or x86_64 "
            "glibc Linux hosts; cross-compilation is not implemented"
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
    if IS_LINUX:
        return _linux_doctor_report(
            metadata, source_input, source_cached, toolchain, target, rust, rustup,
            llvm_archive.is_file() and llvm_prefix_ready,
        )
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


def _rust_problems(rust: dict[str, Any], rustup: str | None) -> list[str]:
    failures: list[str] = []
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
    active = rust.get("active_toolchain", "")
    if rust.get("installed") and not active.startswith(RUST_CHANNEL):
        failures.append(f"rustup did not activate {RUST_CHANNEL} for the build")
    return failures


def _linux_doctor_report(
    metadata: dict[str, Any], source_input: Input, source_cached: bool, toolchain,
    target, rust: dict[str, Any], rustup: str | None, llvm_ready: bool,
) -> dict[str, Any]:
    failures = lane_linux.problems(toolchain)
    failures.extend(_rust_problems(rust, rustup))
    if not source_cached:
        failures.append("the pinned CPython archive is not verified in .cache; run fetch")
    if not llvm_ready:
        failures.append("the locked LLVM 23.1.2 toolchain is not provisioned; run fetch")
    return {
        "host": {
            "os": platform.system(),
            "architecture": platform.machine(),
            "libc": list(platform.libc_ver()),
        },
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
            "clang_path": str(toolchain.clang),
            "clang_version": _tool_output([str(toolchain.clang), "--version"]),
            "llvm_prefix_ready": llvm_ready,
        },
        "host_packages": lane_linux.package_report(toolchain),
        "gnu_make": {"path": str(toolchain.make),
                     "version": _tool_output([str(toolchain.make), "--version"])},
        "pgo_profdata": {
            "path": str(toolchain.llvm_profdata),
            "version": _tool_output([str(toolchain.llvm_profdata), "--version"]),
        },
        "network_sandbox": lane_linux.describe(),
        "problems": failures,
        "ok": not failures,
    }


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


def _source_patch_inputs(*, url_unquote: bool = False,
                         tar_checksum: bool = False,
                         ipv4_scan: bool = False,
                         strptime_numeric: bool = False,
                         uuid_canonical: bool = False,
                         shlex_split: bool = False,
                         fraction_rational: bool = False) -> dict[str, Any]:
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
    optional_patches = {
        "0004-rust-url-unquote.patch": "url-unquote",
        "0005-rust-tar-checksum.patch": "tar-checksum",
        "0006-rust-ipv4-scan.patch": "ipv4-scan",
        "0007-rust-strptime-numeric.patch": "strptime-numeric",
        "0008-rust-uuid-canonical.patch": "uuid-canonical",
        "0009-rust-shlex-split.patch": "shlex-split",
        "0010-rust-fraction-rational.patch": "fraction-rational",
    }
    optional_seen: set[str] = set()
    for entry in manifest["patches"]:
        if not isinstance(entry, dict) or set(entry) not in (required, required | {"mode"}):
            raise LaneError("source patch manifest entry has an invalid schema")
        if any(not isinstance(entry[key], str) or not entry[key].strip() for key in required):
            raise LaneError("source patch manifest entry has an empty or invalid field")
        name = entry["file"]
        mode = entry.get("mode")
        if mode != optional_patches.get(name):
            raise LaneError(f"source patch mode is invalid: {name}")
        if mode is not None:
            optional_seen.add(name)
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
        if mode is None or (mode == "url-unquote" and url_unquote) or (
            mode == "tar-checksum" and tar_checksum
        ) or (
            mode == "ipv4-scan" and ipv4_scan
        ) or (
            mode == "strptime-numeric" and strptime_numeric
        ) or (
            mode == "uuid-canonical" and uuid_canonical
        ) or (
            mode == "shlex-split" and shlex_split
        ) or (
            mode == "fraction-rational" and fraction_rational
        ):
            records.append(dict(entry))
    if optional_seen != set(optional_patches):
        raise LaneError("source patch manifest is missing optional patches: "
                        + ", ".join(sorted(set(optional_patches) - optional_seen)))
    return {
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "source_commit": metadata["commit"],
        "url_unquote": url_unquote,
        "tar_checksum": tar_checksum,
        "ipv4_scan": ipv4_scan,
        "strptime_numeric": strptime_numeric,
        "uuid_canonical": uuid_canonical,
        "shlex_split": shlex_split,
        "fraction_rational": fraction_rational,
        "patches": records,
    }


def _apply_source_patches(source: Path, *, url_unquote: bool = False,
                          tar_checksum: bool = False,
                          ipv4_scan: bool = False,
                          strptime_numeric: bool = False,
                          uuid_canonical: bool = False,
                          shlex_split: bool = False,
                          fraction_rational: bool = False) -> dict[str, Any]:
    """Apply authored patches only to the verified, pinned fresh source tree."""
    inputs = _source_patch_inputs(url_unquote=url_unquote,
                                  tar_checksum=tar_checksum,
                                  ipv4_scan=ipv4_scan,
                                  strptime_numeric=strptime_numeric,
                                  uuid_canonical=uuid_canonical,
                                  shlex_split=shlex_split,
                                  fraction_rational=fraction_rational)
    metadata, _entry = _read_lock()
    expected_lock = metadata["cargo_lock_sha256"]
    if hashlib.sha256((source / "Cargo.lock").read_bytes()).hexdigest() != expected_lock:
        raise LaneError("Cargo.lock digest disagrees with the source lock before patching")
    # The extracted tree can live inside this repository's worktree. Without a
    # ceiling, git apply treats that repository as its own and silently skips
    # every path in a diff --git patch because of the source directory prefix.
    git_env = os.environ.copy()
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_PREFIX"):
        git_env.pop(key, None)
    git_env["GIT_CEILING_DIRECTORIES"] = str(source.parent.resolve())
    for record in inputs["patches"]:
        path = PATCH_MANIFEST.parent / record["file"]
        # These optional scanners anchor insertions on a stable URL module
        # line because other optional modules occupy both sides.
        narrow_context = (["--unidiff-zero"]
                          if record["file"] in {"0009-rust-shlex-split.patch",
                                                "0010-rust-fraction-rational.patch"} else [])
        for check_only in (True, False):
            argv = ["git", "apply", "--whitespace=error", *narrow_context]
            if check_only:
                argv.append("--check")
            argv.append(str(path))
            result = subprocess.run(argv, cwd=source, env=git_env, capture_output=True, text=True)
            if result.returncode != 0:
                detail = (result.stderr or result.stdout).strip()
                raise LaneError(f"source patch {record['file']} does not apply: {detail}")
        # A zero exit status alone is insufficient: git apply may skip all
        # paths and still report success. The applied patch must now reverse.
        reverse = subprocess.run(
            ["git", "apply", "--reverse", "--check", *narrow_context, str(path)],
            cwd=source, env=git_env, capture_output=True, text=True,
        )
        if reverse.returncode != 0:
            detail = (reverse.stderr or reverse.stdout).strip()
            raise LaneError(f"source patch {record['file']} did not change the source: {detail}")
        forward = subprocess.run(
            ["git", "apply", "--check", *narrow_context, str(path)],
            cwd=source, env=git_env, capture_output=True, text=True,
        )
        if forward.returncode == 0:
            raise LaneError(f"source patch {record['file']} did not change the source")
    if hashlib.sha256((source / "Cargo.lock").read_bytes()).hexdigest() != expected_lock:
        raise LaneError("source patches changed the pinned Cargo.lock")
    return inputs


def _llvm_layout():
    return LINUX_X86_64_LAYOUT if IS_LINUX else MACOS_AARCH64_LAYOUT


def _llvm_ready(toolchain) -> Path:
    llvm_cache = Cache(CACHE_ROOT / "llvm")
    if IS_LINUX:
        deb = llvm_cache.require(toolchain.icu_input())
        lane_linux.provision_icu_runtime(toolchain, deb)
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
        layout=_llvm_layout(),
    )


def _fetch_llvm(toolchain) -> Path:
    llvm_cache = Cache(CACHE_ROOT / "llvm")
    if IS_LINUX:
        prefix = _fetch_llvm_archive(toolchain, llvm_cache)
        try:
            deb = llvm_cache.fetch(toolchain.icu_input())
            lane_linux.provision_icu_runtime(toolchain, deb)
        except (InputError, OSError, lane_linux.LinuxHostError) as error:
            raise LaneError(f"cannot provision the ld.lld ICU runtime: {error}") from error
        return prefix
    return _fetch_llvm_archive(toolchain, llvm_cache)


def _fetch_llvm_archive(toolchain, llvm_cache: Cache) -> Path:
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
            layout=_llvm_layout(),
        )
    except (InputError, OSError, ValueError) as error:
        raise LaneError(f"cannot provision the locked LLVM toolchain: {error}") from error


def _environment(toolchain, *, offline: bool, build_dir: Path | None = None) -> dict[str, str]:
    if build_dir is None:
        build_dir = BUILD
    rustup = shutil.which("rustup")
    rustup_directory = str(Path(rustup).parent) if rustup else "/usr/bin"
    cargo_bin = CARGO_HOME / "bin"
    llvm_bin = toolchain.llvm_prefix / "bin"
    path_parts = [
        str(cargo_bin), str(llvm_bin), rustup_directory,
        *(() if IS_LINUX else ("/opt/homebrew/bin",)),
        "/usr/bin", "/bin", "/usr/sbin", "/sbin",
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
    # A host egress proxy changes urllib/http.client test behavior; the
    # regression suite runs against direct loopback servers only.
    for name in tuple(env):
        if name.lower() in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}:
            env.pop(name)
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
    """Use the pinned zlib-rs source for the optional whole-build candidate."""
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
            or entry.role != "build-source" or entry.target not in LANE_TARGETS
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


def _zlib_cargo_env(toolchain, *, offline: bool, hybrid: bool = False) -> dict[str, str]:
    env = _environment(toolchain, offline=offline)
    env["CARGO_TARGET_DIR"] = str(ZLIB_TARGET)
    for key in ("RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER"):
        env.pop(key, None)
    if hybrid:
        env["LIBZ_RS_SYS_PREFIX"] = ZLIB_HYBRID_PREFIX
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


def _build_zlib(toolchain, sandbox: SealedRun, *, hybrid: bool = False,
                oneshot: bool = False) -> dict[str, Any]:
    metadata, entry = _zlib_input()
    blob = Cache(CACHE_ROOT).require(entry)
    source = _zlib_source(blob)
    command = [str(CARGO_HOME / "bin" / "cargo"), "build", "--release", "--locked",
               "--offline", "--manifest-path", str(source / "Cargo.toml")]
    if hybrid or oneshot:
        command.extend(("--features", "custom-prefix"))
    _require_command(
        command,
        cwd=source, env=sandbox.environment(_zlib_cargo_env(toolchain, offline=True, hybrid=hybrid or oneshot)),
        log=LOGS / "zlib-candidate-build.log",
        sealed=sandbox,
    )
    if hashlib.sha256((source / "Cargo.lock").read_bytes()).hexdigest() != metadata["cargo_lock_sha256"]:
        raise LaneError("zlib-rs Cargo.lock changed during build")
    if not ZLIB_ARCHIVE.is_file():
        raise LaneError(f"zlib-rs did not produce {ZLIB_ARCHIVE}")
    if hybrid or oneshot:
        symbols = _command([str(toolchain.llvm_prefix / "bin" / "llvm-nm"),
                            "-g", "--defined-only", str(ZLIB_ARCHIVE)])
        if symbols["returncode"] != 0:
            raise LaneError(f"cannot inspect hybrid archive symbols: {symbols['output']}")
        for symbol in ("inflate", "inflateInit2_", "inflateEnd", "inflateCopy", "inflateSetDictionary"):
            if re.search(rf"(?m)\b{SYMBOL_PREFIX}{ZLIB_HYBRID_PREFIX}{symbol}$", symbols["output"]) is None:
                raise LaneError(f"hybrid archive lacks prefixed {symbol}")
        if re.search(rf"(?m)\b{SYMBOL_PREFIX}(?:deflate\w*|inflate\w*|zlibVersion)$",
                     symbols["output"]):
            raise LaneError("hybrid archive defines an unprefixed zlib entry point")
    return {
        "kind": "oneshot-inflate" if oneshot else "hybrid-inflate" if hybrid else "full-rust",
        "symbol_prefix": ZLIB_HYBRID_PREFIX if hybrid or oneshot else "",
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
        source_blob, route = lane_linux.fetch_source(Cache(CACHE_ROOT), source_input)
    except (InputError, OSError) as error:
        raise LaneError(f"cannot fetch the pinned CPython source: {error}") from error
    print(f"OK    source archive ({route}) -> {source_blob}")
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


def _platform_flags(toolchain, target, prefix: Path | None = None) -> dict[str, str]:
    """C, C++, preprocessor, linker and pkg-config inputs for the host target.

    Linux binaries find libpython through an absolute runpath to the build's
    own install prefix, matching the macOS lane's absolute install names. An
    `$ORIGIN` runpath is not usable: the fork's cargo rule passes the linker
    arguments through a double-quoted shell word, which expands it away.
    """
    if prefix is None:
        prefix = STAGE
    if IS_LINUX:
        flags = " ".join(("-O3", target.cpu_baseline_cflag, "-fPIC"))
        return {
            "CFLAGS": flags,
            "CXXFLAGS": flags,
            "CPPFLAGS": "",
            "PY_CPPFLAGS": "",
            "LDFLAGS": f"-fuse-ld=lld -Wl,-rpath,{Path(prefix) / 'lib'}",
            "PKG_CONFIG_PATH": "",
        }
    flags = " ".join((
        "-O3", target.cpu_baseline_cflag, "-fPIC",
        f"-mmacosx-version-min={toolchain.deployment_target}",
    ))
    return {
        "CFLAGS": flags,
        "CXXFLAGS": flags,
        "CPPFLAGS": f"-isysroot {toolchain.sdkroot}",
        "PY_CPPFLAGS": f"-isysroot {toolchain.sdkroot}",
        "LDFLAGS": f"-mmacosx-version-min={toolchain.deployment_target}",
        "PKG_CONFIG_PATH": _brew_pkg_config_path(),
    }


def _cargo_linker_variable() -> str:
    return f"CARGO_TARGET_{TARGET.upper().replace('-', '_')}_LINKER"


def _configuration(toolchain, target, jobs: int, *, zlib_archive: Path | None = None,
                   zlib_hybrid: bool = False, zlib_oneshot: bool = False) -> tuple[list[str], dict[str, str]]:
    profile_task = _profile_task(jobs)
    platform_flags = _platform_flags(toolchain, target)
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
    env.update(platform_flags)
    env.update({
        "PROFILE_TASK": profile_task,
        "LLVM_PROFDATA": str(toolchain.llvm_profdata),
    })
    if zlib_archive is not None:
        env["ZLIB_LIBS"] = f"-lz {zlib_archive}" if zlib_hybrid or zlib_oneshot else str(zlib_archive)
    if zlib_hybrid:
        env["CFLAGS"] += " -DPYTHON_BUILD_ZLIB_HYBRID=1"
    if zlib_oneshot:
        env["CFLAGS"] += " -DPYTHON_BUILD_ZLIB_ONESHOT=1"
    return args, env


def _sealed_sandbox():
    """The offline boundary for this host, proven against a live listener."""
    if IS_LINUX:
        return _linux_sandbox()
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


def _linux_sandbox() -> "lane_linux.SealedRun":
    sandbox = lane_linux.SealedRun(write_paths=[LANE], home=LANE / ".home")
    try:
        proof = lane_linux.network_boundary_selftest(Path(sys.executable), WORK / "sandbox-probe")
    except (lane_linux.LinuxHostError, OSError, subprocess.SubprocessError) as error:
        raise LaneError(f"cannot prove the offline network boundary: {error}") from error
    if not proof.get("ok"):
        raise LaneError(f"namespace network-denial self-test failed: {proof}")
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


LINUX_ELF_MACHINE = "Advanced Micro Devices X86-64"


def _binary_identity(path: Path, toolchain) -> dict[str, Any]:
    """Architecture, deployment floor, and dynamic references of one binary."""
    if IS_LINUX:
        machine = lane_linux.elf_machine(toolchain, path)
        if machine != LINUX_ELF_MACHINE:
            raise LaneError(f"{path.name} ELF machine is {machine!r}, expected x86-64")
        dynamic = lane_linux.elf_dynamic(toolchain, path)
        return {"arch": "x86_64", "minos": "", "dependencies": dynamic["needed"],
                "rpaths": dynamic["rpaths"]}
    header = macho.read_header(path)
    version = macho.build_version(path)
    if header.arch != "arm64":
        raise LaneError(f"{path.name} architecture is {header.arch}, expected arm64")
    if version is None or version.minos != toolchain.deployment_target:
        raise LaneError(
            f"{path.name} deployment floor is {version.minos if version else None}, "
            f"expected {toolchain.deployment_target}"
        )
    return {"arch": header.arch, "minos": version.minos,
            "dependencies": macho.dependencies(path), "rpaths": macho.rpaths(path)}


def _check_linux_interpreter(python: Path, toolchain) -> None:
    """The installed interpreter must find libpython relative to itself."""
    dynamic = lane_linux.elf_dynamic(toolchain, python.resolve())
    # configure repeats LDFLAGS on the link line, so the entry can repeat.
    entries = {entry for value in dynamic["rpaths"] for entry in value.split(":")}
    if entries != {str(STAGE / "lib")}:
        raise LaneError(f"installed interpreter runpath is {dynamic['rpaths']!r}")
    if not any(name.startswith("libpython3.16") for name in dynamic["needed"]):
        raise LaneError("installed interpreter does not link the shared libpython")
    allowed = {str(STAGE / "lib")}
    for binary in sorted((STAGE / "lib").glob("**/*.so*")):
        if binary.is_symlink() or not binary.is_file():
            continue
        runpaths = lane_linux.elf_dynamic(toolchain, binary)["rpaths"]
        found = {entry for value in runpaths for entry in value.split(":")}
        if not found <= allowed:
            raise LaneError(f"{binary.relative_to(STAGE)} has unexpected runpath {sorted(found)}")


def _defined_symbols(path: Path, toolchain) -> str:
    symbols = _command([
        str(toolchain.llvm_prefix / "bin" / "llvm-nm"), "-g", "--defined-only", str(path),
    ])
    if symbols["returncode"] != 0:
        raise LaneError(f"cannot inspect symbols of {path}: {symbols['output']}")
    return str(symbols["output"])


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

    binary = _binary_identity(module_path, toolchain)
    dependencies = binary["dependencies"]
    rpaths = binary["rpaths"]
    if IS_LINUX:
        _check_linux_interpreter(python, toolchain)
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
    interpreter["module_arch"] = binary["arch"]
    interpreter["module_minos"] = binary["minos"]
    return interpreter


def _zlib_module_report(python: Path, toolchain, *, hybrid: bool = False,
                        oneshot: bool = False) -> dict[str, Any]:
    """Prove the installed whole-build module uses the candidate C ABI."""
    code = (
        "import binascii,json,zlib; "
        "payload=bytes(range(256))*4096; "
        "assert zlib.decompress(zlib.compress(payload))==payload; "
        "assert binascii.crc32(payload)==zlib.crc32(payload); "
        "print(json.dumps({'path':zlib.__file__,"
        "'binascii_path':binascii.__file__,"
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
    expected_version = PLATFORM_ZLIB_VERSION if hybrid or oneshot else "1.3.0-zlib-rs-0.6.7"
    if identity["runtime_version"] != expected_version:
        raise LaneError(f"installed zlib runtime is not the pinned backend: {identity['runtime_version']!r}")
    module = Path(identity["path"]).resolve()
    try:
        module.relative_to(STAGE.resolve())
    except ValueError as error:
        raise LaneError(f"zlib module was loaded outside the stage tree: {module}") from error
    if not module.is_file():
        raise LaneError(f"installed zlib module is missing: {module}")
    dependencies = _binary_identity(module, toolchain)["dependencies"]
    if (PLATFORM_LIBZ in dependencies) != (hybrid or oneshot):
        raise LaneError("installed zlib module has the wrong platform libz dependency")
    defined = _defined_symbols(module, toolchain)
    prefixed = ("inflateInit2_", "inflate", "inflateEnd") if oneshot else (
        "inflateInit2_", "inflate", "inflateEnd", "inflateCopy", "inflateSetDictionary"
    )
    expected_symbols = (tuple(f"{SYMBOL_PREFIX}{ZLIB_HYBRID_PREFIX}{name}" for name in prefixed)
                        if hybrid or oneshot else
                        tuple(f"{SYMBOL_PREFIX}{name}" for name in
                              ("zlibVersion", "deflateInit2_", "inflateInit2_")))
    for symbol in expected_symbols:
        if re.search(rf"(?m)\b{symbol}$", defined) is None:
            raise LaneError(f"installed zlib module lacks static backend symbol {symbol}")
    if (hybrid or oneshot) and re.search(
        rf"(?m)\b{SYMBOL_PREFIX}(?:deflate\w*|inflate\w*|zlibVersion)$", defined
    ):
        raise LaneError("mixed zlib module defines platform zlib symbols")
    platform_refs: list[str] = []
    if oneshot:
        undefined = _command([
            str(toolchain.llvm_prefix / "bin" / "llvm-nm"), "-u", str(module),
        ])
        if undefined["returncode"] != 0:
            raise LaneError(f"cannot inspect installed zlib references: {undefined['output']}")
        platform_refs = [f"{SYMBOL_PREFIX}{name}" for name in
                         ("inflateInit2_", "inflate", "inflateEnd", "inflateCopy",
                          "inflateSetDictionary")]
        for symbol in platform_refs:
            if re.search(rf"(?m)\b{symbol}$", undefined["output"]) is None:
                raise LaneError(f"one-shot zlib module lacks platform reference {symbol}")
    binascii = Path(identity.pop("binascii_path")).resolve()
    try:
        binascii.relative_to(STAGE.resolve())
    except ValueError as error:
        raise LaneError(f"binascii module was loaded outside the stage tree: {binascii}") from error
    if not binascii.is_file():
        raise LaneError(f"installed binascii module is missing: {binascii}")
    binascii_dependencies = _binary_identity(binascii, toolchain)["dependencies"]
    if PLATFORM_LIBZ not in binascii_dependencies:
        raise LaneError("installed binascii module does not use platform libz")
    binascii_defined = _defined_symbols(binascii, toolchain)
    for name in ("crc32", "adler32", "zlibVersion"):
        if re.search(rf"(?m)\b{SYMBOL_PREFIX}{name}$", binascii_defined):
            raise LaneError(f"installed binascii still defines static backend symbol {name}")
    return {
        **identity,
        "path": str(module),
        "sha256": hashlib.sha256(module.read_bytes()).hexdigest(),
        "size": module.stat().st_size,
        "dynamic_dependencies": dependencies,
        "static_backend_symbols": [symbol[len(SYMBOL_PREFIX):] for symbol in expected_symbols],
        **({"platform_inflate_references": [symbol[len(SYMBOL_PREFIX):] for symbol in platform_refs]}
           if oneshot else {}),
        "python_wrapper": "one-shot inflate on prefixed Rust, streaming inflate on platform libz" if oneshot else
                          "conditional inflate routing in pinned CPython Modules/zlibmodule.c" if hybrid else
                          "pinned CPython Modules/zlibmodule.c with inactive hybrid guard",
        "binascii": {
            "path": str(binascii),
            "sha256": hashlib.sha256(binascii.read_bytes()).hexdigest(),
            "size": binascii.stat().st_size,
            "dynamic_dependencies": binascii_dependencies,
            "backend": "platform libz",
            "static_backend_symbols": [],
        },
    }


def _select_platform_binascii(makefile: Path, *, hybrid: bool = False) -> dict[str, str]:
    """Narrow configure's shared zlib input to the zlib extension alone.

    The pinned CPython configure derives BINASCII_LIBS from ZLIB_LIBS. Rewrite
    only the generated binascii link variable after checking both module
    variables, and retain the before/after Makefile digests as recipe evidence.
    """
    if _make_value(makefile, "MODULE_ZLIB_STATE") != "yes":
        raise LaneError("configure did not enable the zlib extension")
    if _make_value(makefile, "MODULE_BINASCII_STATE") != "yes":
        raise LaneError("configure did not enable the binascii extension")
    zlib_flags = f"-lz {ZLIB_ARCHIVE}" if hybrid else str(ZLIB_ARCHIVE)
    for name in ("MODULE_ZLIB_LDFLAGS", "MODULE_BINASCII_LDFLAGS"):
        found = _make_value(makefile, name)
        if found != zlib_flags:
            raise LaneError(f"configure did not preserve the pinned zlib archive in {name}: {found!r}")
    original = makefile.read_bytes()
    needle = f"MODULE_BINASCII_LDFLAGS={zlib_flags}\n".encode()
    if original.count(needle) != 1:
        raise LaneError("cannot locate one exact binascii link variable in generated Makefile")
    modified = original.replace(needle, b"MODULE_BINASCII_LDFLAGS=-lz\n")
    makefile.write_bytes(modified)
    if (_make_value(makefile, "MODULE_ZLIB_LDFLAGS") != zlib_flags
            or _make_value(makefile, "MODULE_BINASCII_LDFLAGS") != "-lz"):
        raise LaneError("generated Makefile did not retain the distinct zlib/binascii link inputs")
    return {
        "configured_makefile_sha256": hashlib.sha256(original).hexdigest(),
        "effective_makefile_sha256": hashlib.sha256(modified).hexdigest(),
        "zlib_ldflags": zlib_flags,
        "binascii_ldflags": "-lz",
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


def _configure_source(source: Path, toolchain, target, jobs: int, sandbox: SealedRun, patches: dict[str, Any], zlib_backend: dict[str, Any] | None = None, *, zlib_hybrid: bool = False, zlib_oneshot: bool = False, tar_checksum: bool = False, ipv4_scan: bool = False, strptime_numeric: bool = False, uuid_canonical: bool = False, shlex_split: bool = False, fraction_rational: bool = False) -> dict[str, Any]:
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
        zlib_hybrid=zlib_hybrid,
        zlib_oneshot=zlib_oneshot,
    )
    env.update({
        "PY_CC": str(toolchain.llvm_prefix / "bin" / "clang"),
        "PY_CPPFLAGS": env["CPPFLAGS"],
        "PY_CFLAGS": env["CFLAGS"],
        "PYTHON_BUILD_DIR": str(BUILD),
        _cargo_linker_variable(): str(toolchain.llvm_prefix / "bin" / "clang"),
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
        zlib_backend["module_link_recipe"] = _select_platform_binascii(BUILD / "Makefile", hybrid=zlib_hybrid or zlib_oneshot)
    (BUILD / "Modules" / "_rust_url_quote").mkdir(parents=True, exist_ok=True)
    if tar_checksum:
        (BUILD / "Modules" / "_rust_tar_checksum").mkdir(parents=True, exist_ok=True)
    if ipv4_scan:
        (BUILD / "Modules" / "_rust_ipv4_scan").mkdir(parents=True, exist_ok=True)
    if strptime_numeric:
        (BUILD / "Modules" / "_rust_strptime_numeric").mkdir(parents=True, exist_ok=True)
    if uuid_canonical:
        (BUILD / "Modules" / "_rust_uuid_canonical").mkdir(parents=True, exist_ok=True)
    if shlex_split:
        (BUILD / "Modules" / "_rust_shlex_split").mkdir(parents=True, exist_ok=True)
    if fraction_rational:
        (BUILD / "Modules" / "_rust_fraction_rational").mkdir(parents=True, exist_ok=True)
    make = [str(toolchain.make), f"-j{jobs}"]
    _require_command(
        make, cwd=BUILD, env=source_date_env,
        log=LOGS / "cpython-build.log", sealed=sandbox,
    )
    if zlib_backend is not None and _make_value(BUILD / "Makefile", "MODULE_BINASCII_LDFLAGS") != "-lz":
        raise LaneError("CPython build regenerated the binascii platform link setting")
    _require_command(
        [str(toolchain.make), "install"], cwd=BUILD, env=source_date_env,
        log=LOGS / "cpython-install.log", sealed=sandbox,
    )
    if zlib_backend is not None and _make_value(BUILD / "Makefile", "MODULE_BINASCII_LDFLAGS") != "-lz":
        raise LaneError("CPython install regenerated the binascii platform link setting")
    python = STAGE / "bin" / "python3.16"
    if not python.is_file():
        raise LaneError(f"CPython install did not produce {python}")
    module = _module_report(STAGE, python, toolchain)
    if zlib_backend is not None:
        zlib_backend["installed_module"] = _zlib_module_report(python, toolchain, hybrid=zlib_hybrid,
                                                                 oneshot=zlib_oneshot)
    cargo_env = dict(source_date_env)
    cargo_env.update({
        "PYTHON_BUILD_DIR": str(BUILD),
        "PY_CC": str(toolchain.llvm_prefix / "bin" / "clang"),
        "PY_CPPFLAGS": source_date_env["CPPFLAGS"],
        "PY_CFLAGS": source_date_env["CFLAGS"],
        "CARGO_TARGET_DIR": str(BUILD / "target"),
        "LLVM_TARGET": TARGET,
        "RUST_SHARED_BUILD": "1",
        _cargo_linker_variable(): str(toolchain.llvm_prefix / "bin" / "clang"),
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
        "sdk": _platform_sdk_report(toolchain),
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
            "mechanism": (lane_linux.describe()["mechanism"] if IS_LINUX
                          else "sandbox-exec with deny network*"),
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


def _platform_sdk_report(toolchain) -> dict[str, Any]:
    if IS_LINUX:
        return {"host_packages": lane_linux.package_report(toolchain),
                "libc": list(platform.libc_ver())}
    return {
        "path": str(toolchain.sdkroot),
        "version": sdk_version(toolchain.sdkroot),
        "xcode_version": toolchain.xcode_version,
    }


def _unpatched_record() -> dict[str, Any]:
    inputs = _source_patch_inputs()
    return {**inputs, "patches": [], "skipped_manifest_patches": [
        record["file"] for record in inputs["patches"]]}


def build(*, zlib_rs: bool = False, zlib_hybrid: bool = False,
          zlib_oneshot: bool = False, url_unquote: bool = False,
          tar_checksum: bool = False, ipv4_scan: bool = False,
          strptime_numeric: bool = False,
          uuid_canonical: bool = False, shlex_split: bool = False,
          fraction_rational: bool = False,
          apply_patches: bool = True) -> int:
    if sum((zlib_rs, zlib_hybrid, zlib_oneshot)) > 1:
        raise LaneError("select one zlib candidate mode")
    _require_host()
    doctor = doctor_report()
    if not doctor["ok"]:
        raise LaneError("doctor found prerequisites missing; run doctor for details")
    rustup = _require_nightly()
    _cargo_wrapper(rustup)
    toolchain, target = _toolchain()
    _llvm_ready(toolchain)
    sandbox = _sealed_sandbox() if (zlib_rs or zlib_hybrid or zlib_oneshot) else None
    zlib_backend = _build_zlib(toolchain, sandbox, hybrid=zlib_hybrid,
                               oneshot=zlib_oneshot) if sandbox is not None else None
    source = _extract_fresh(SOURCE)
    wrapper = source / "Modules" / "zlibmodule.c"
    wrapper_sha256 = hashlib.sha256(wrapper.read_bytes()).hexdigest() if zlib_backend else None
    if (url_unquote or tar_checksum or ipv4_scan or strptime_numeric
            or uuid_canonical or shlex_split or fraction_rational) and not apply_patches:
        raise LaneError("optional source patches require source patches")
    patches = (_apply_source_patches(source, url_unquote=url_unquote,
                                     tar_checksum=tar_checksum,
                                     ipv4_scan=ipv4_scan,
                                     strptime_numeric=strptime_numeric,
                                     uuid_canonical=uuid_canonical,
                                     shlex_split=shlex_split,
                                     fraction_rational=fraction_rational)
               if apply_patches else _unpatched_record())
    if zlib_backend is not None:
        zlib_backend["cpython_zlibmodule_source_sha256"] = wrapper_sha256
        zlib_backend["cpython_zlibmodule_sha256"] = hashlib.sha256(wrapper.read_bytes()).hexdigest()
        if zlib_backend["cpython_zlibmodule_sha256"] == wrapper_sha256:
            raise LaneError("candidate source patch did not change Modules/zlibmodule.c")
    env = _environment(toolchain, offline=True)
    _require_command(
        [str(CARGO_HOME / "bin" / "cargo"), "fetch", "--locked", "--offline",
         "--manifest-path", str(source / "Cargo.toml")],
        cwd=source, env=env, log=LOGS / "cargo-offline-check.log",
    )
    if sandbox is None:
        sandbox = _sealed_sandbox()
    jobs = max(1, (os.cpu_count() or 4) - 1)
    report = _configure_source(source, toolchain, target, jobs, sandbox, patches, zlib_backend,
                               zlib_hybrid=zlib_hybrid, zlib_oneshot=zlib_oneshot,
                               tar_checksum=tar_checksum, ipv4_scan=ipv4_scan,
                               strptime_numeric=strptime_numeric,
                               uuid_canonical=uuid_canonical,
                               shlex_split=shlex_split,
                               fraction_rational=fraction_rational)
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
    recorded_patches = report["source"].get("patches")
    if (not isinstance(recorded_patches, dict)
            or type(recorded_patches.get("url_unquote")) is not bool
            or type(recorded_patches.get("tar_checksum")) is not bool
            or type(recorded_patches.get("ipv4_scan")) is not bool
            or type(recorded_patches.get("strptime_numeric")) is not bool
            or type(recorded_patches.get("uuid_canonical")) is not bool
            or type(recorded_patches.get("shlex_split")) is not bool
            or type(recorded_patches.get("fraction_rational")) is not bool):
        raise LaneError("build report is missing optional source patch selections")
    url_unquote = recorded_patches["url_unquote"]
    tar_checksum = recorded_patches["tar_checksum"]
    ipv4_scan = recorded_patches["ipv4_scan"]
    strptime_numeric = recorded_patches["strptime_numeric"]
    uuid_canonical = recorded_patches["uuid_canonical"]
    shlex_split = recorded_patches["shlex_split"]
    fraction_rational = recorded_patches["fraction_rational"]
    applied = bool(recorded_patches.get("patches"))
    patches = (_source_patch_inputs(url_unquote=url_unquote,
                                    tar_checksum=tar_checksum,
                                    ipv4_scan=ipv4_scan,
                                    strptime_numeric=strptime_numeric,
                                    uuid_canonical=uuid_canonical,
                                    shlex_split=shlex_split,
                                    fraction_rational=fraction_rational)
               if applied else _unpatched_record())
    if report["source"].get("patches") != patches:
        raise LaneError("current source patches disagree with the completed build report")
    source = SOURCE
    if not (source / "Cargo.toml").is_file():
        source = _extract_fresh(SOURCE)
        if applied:
            _apply_source_patches(source, url_unquote=url_unquote,
                                  tar_checksum=tar_checksum,
                                  ipv4_scan=ipv4_scan,
                                  strptime_numeric=strptime_numeric,
                                  uuid_canonical=uuid_canonical,
                                  shlex_split=shlex_split,
                                  fraction_rational=fraction_rational)
    toolchain, _target = _toolchain()
    rustup = _require_nightly()
    _cargo_wrapper(rustup)
    env = _test_environment(toolchain)
    env.update({
        "PYTHON_BUILD_DIR": str(BUILD),
        "PY_CC": str(toolchain.llvm_prefix / "bin" / "clang"),
        "PY_CPPFLAGS": _platform_flags(toolchain, _target)["PY_CPPFLAGS"],
        "PY_CFLAGS": env.get("CFLAGS", ""),
        "CARGO_TARGET_DIR": str(BUILD / "target"),
        "LLVM_TARGET": TARGET,
        "RUST_SHARED_BUILD": "1",
        _cargo_linker_variable(): str(toolchain.llvm_prefix / "bin" / "clang"),
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
    for path in (WORK, STAGE, LOGS, RESULTS, LANE / ".home", *LANE.glob("stage-*")):
        if path.exists():
            shutil.rmtree(path)
    print(f"OK    removed work, stage, logs, and results; kept private Cargo registry at {CARGO_HOME}")
    return 0


def restore_default_signals() -> None:
    """Undo an inherited ignored SIGINT/SIGQUIT before running build commands.

    A shell starts background jobs with SIGINT and SIGQUIT ignored, and
    ignored dispositions survive exec. CPython then leaves SIGINT ignored, so
    the PGO task's signal tests fail and the recorded profile would depend on
    how the builder was launched. Handlers reset to default across exec.
    """
    if signal.getsignal(signal.SIGINT) == signal.SIG_IGN:
        signal.signal(signal.SIGINT, signal.default_int_handler)
    if signal.getsignal(signal.SIGQUIT) == signal.SIG_IGN:
        signal.signal(signal.SIGQUIT, signal.SIG_DFL)


def main(argv: list[str] | None = None) -> int:
    restore_default_signals()
    parser = argparse.ArgumentParser(description="Isolated Rust-for-CPython 3.16 experiment")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("doctor", "report host, source, and toolchain readiness"),
        ("fetch", "fetch locked sources and Cargo dependencies"),
        ("build", "build and validate the native interpreter offline"),
        ("test", "run Rust and CPython tests"),
        ("clean", "remove build outputs while keeping the private Cargo cache"),
    ):
        command_parser = subparsers.add_parser(name, help=help_text)
        if name in ("fetch", "build"):
            command_parser.add_argument(
                "--zlib-rs", action="store_true",
                help="include pinned zlib-rs 0.6.7 in this optional candidate build",
            )
            command_parser.add_argument(
                "--zlib-hybrid", action="store_true",
                help="use prefixed zlib-rs inflate with platform zlib compression",
            )
            command_parser.add_argument(
                "--zlib-oneshot", action="store_true",
                help="use prefixed zlib-rs only for one-shot decompression",
            )
        if name in ("build", "test"):
            command_parser.add_argument(
                "--variant", default="",
                help="build into work/variants/NAME and stage-NAME instead of stage/",
            )
        if name == "build":
            command_parser.add_argument(
                "--no-patches", action="store_true",
                help="build the pinned fork without the manifest source patches",
            )
            command_parser.add_argument(
                "--url-unquote", action="store_true",
                help="include the optional Rust URL percent decoder",
            )
            command_parser.add_argument(
                "--tar-checksum", action="store_true",
                help="include the optional Rust exact TAR header checksum scan",
            )
            command_parser.add_argument(
                "--ipv4-scan", action="store_true",
                help="include the optional Rust canonical IPv4 literal scan",
            )
            command_parser.add_argument(
                "--strptime-numeric", action="store_true",
                help="include the optional Rust fixed-width numeric timestamp scan",
            )
            command_parser.add_argument(
                "--uuid-canonical", action="store_true",
                help="include the optional Rust canonical UUID text scanner",
            )
            command_parser.add_argument(
                "--shlex-split", action="store_true",
                help="include the optional Rust POSIX shlex split scanner",
            )
            command_parser.add_argument(
                "--fraction-rational", action="store_true",
                help="include the optional Rust canonical rational text scanner",
            )
    args = parser.parse_args(argv)
    commands = {"doctor": doctor, "fetch": fetch, "build": build, "test": test, "clean": clean}
    try:
        _select_variant(getattr(args, "variant", ""))
        if args.command in ("fetch", "build"):
            if sum((args.zlib_rs, args.zlib_hybrid, args.zlib_oneshot)) > 1:
                raise LaneError("select one zlib candidate mode")
            if args.command == "fetch":
                return fetch(zlib_rs=args.zlib_rs or args.zlib_hybrid or args.zlib_oneshot)
            return build(zlib_rs=args.zlib_rs, zlib_hybrid=args.zlib_hybrid,
                         zlib_oneshot=args.zlib_oneshot, url_unquote=args.url_unquote,
                         tar_checksum=args.tar_checksum, ipv4_scan=args.ipv4_scan,
                         strptime_numeric=args.strptime_numeric,
                         uuid_canonical=args.uuid_canonical,
                         shlex_split=args.shlex_split,
                         fraction_rational=args.fraction_rational,
                         apply_patches=not args.no_patches)
        return commands[args.command]()
    except (LaneError, InputError, BootstrapError, SandboxError, OSError, ValueError) as error:
        print(f"FAIL  {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
