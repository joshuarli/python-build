#!/usr/bin/env python3
"""Build and test a zlib-rs backend under CPython's unchanged zlib module."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib
from typing import Any

PROOF = Path(__file__).resolve().parent
LANE = PROOF.parent
REPO = LANE.parent
sys.path.insert(0, str(REPO))

from buildsys.inputs import Cache, Input, InputError, load_lock, safe_extract  # noqa: E402

_BUILD_SPEC = importlib.util.spec_from_file_location(
    "rust_cpython_build", LANE / "build.py"
)
if _BUILD_SPEC is None or _BUILD_SPEC.loader is None:
    raise RuntimeError("cannot load the Rust-for-CPython build helpers")
BUILD_LANE = importlib.util.module_from_spec(_BUILD_SPEC)
sys.modules[_BUILD_SPEC.name] = BUILD_LANE
_BUILD_SPEC.loader.exec_module(BUILD_LANE)

SOURCE_LOCK = PROOF / "sources.lock.json"
WORK = LANE / "work" / "zlib-proof"
BACKEND_SOURCE = WORK / "source"
BACKEND_TARGET = WORK / "target"
BACKEND_LIB = WORK / "backend"
OVERLAY = WORK / "overlay"
LOGS = LANE / "logs"
RESULT = LANE / "results" / "zlib-proof.json"

CONTROL_BUILD = LANE / "work" / "build-no-rust"
CONTROL_STAGE = LANE / "stage-no-rust"
CONTROL_REPORT = LANE / "results" / "no-rust-build.json"
CPYTHON_TESTS = (
    "test_zlib",
    "test_gzip",
    "test_tarfile",
    "test_zipfile",
    "test_zipimport",
    "test_binascii",
)
RUST_RUNTIME_VERSION = "1.3.0-zlib-rs-0.6.7"


class ProofError(Exception):
    """The isolated zlib-rs proof cannot safely continue."""


def _source_lock() -> tuple[dict[str, Any], Input]:
    try:
        document = json.loads(SOURCE_LOCK.read_text())
        metadata = document["backend"]
        entries = load_lock(SOURCE_LOCK)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, InputError) as error:
        raise ProofError(f"cannot read zlib proof source lock: {error}") from error
    if len(entries) != 1:
        raise ProofError(f"{SOURCE_LOCK}: expected exactly one backend source")
    entry = entries[0]
    expected = {
        "repository": "https://github.com/trifectatechfoundation/zlib-rs",
        "crate": "libz-rs-sys-cdylib",
        "version": "0.6.7",
        "license": "Zlib",
    }
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise ProofError(f"{SOURCE_LOCK}: backend metadata disagrees with the proof pin")
    if (
        entry.name != metadata["crate"]
        or entry.version != metadata["version"]
        or entry.role != "build-source"
        or entry.target != BUILD_LANE.TARGET
        or entry.license != metadata["license"]
    ):
        raise ProofError(f"{SOURCE_LOCK}: input metadata and backend pin disagree")
    return metadata, entry


def _extract_source(blob: Path, *, fresh: bool) -> Path:
    if fresh and BACKEND_SOURCE.exists():
        shutil.rmtree(BACKEND_SOURCE)
    if not BACKEND_SOURCE.exists():
        safe_extract(blob, BACKEND_SOURCE)
    roots = [path for path in BACKEND_SOURCE.iterdir() if path.is_dir()]
    if len(roots) != 1:
        raise ProofError(
            f"expected one crate root beneath {BACKEND_SOURCE}, found {len(roots)}"
        )
    package = roots[0]
    manifest = package / "Cargo.toml"
    lock = package / "Cargo.lock"
    if not manifest.is_file() or not lock.is_file():
        raise ProofError("the locked zlib-rs crate archive lacks Cargo.toml or Cargo.lock")
    metadata, _entry = _source_lock()
    manifest_data = tomllib.loads(manifest.read_text())
    package_data = manifest_data.get("package", {})
    if (
        package_data.get("name") != metadata["crate"]
        or package_data.get("version") != metadata["version"]
        or package_data.get("license") != metadata["license"]
    ):
        raise ProofError("the zlib-rs crate manifest does not match its source lock")
    found_lock_hash = hashlib.sha256(lock.read_bytes()).hexdigest()
    if found_lock_hash != metadata["cargo_lock_sha256"]:
        raise ProofError(
            "the zlib-rs Cargo.lock digest differs from the proof pin: "
            f"{found_lock_hash} != {metadata['cargo_lock_sha256']}"
        )
    crate_types = manifest_data.get("lib", {}).get("crate-type", [])
    if "staticlib" not in crate_types:
        raise ProofError("the pinned zlib-rs package no longer declares a static library")
    return package


def _cargo_env(toolchain, *, offline: bool, build_dir: Path) -> dict[str, str]:
    env = BUILD_LANE._environment(toolchain, offline=offline, build_dir=build_dir)
    env["CARGO_TARGET_DIR"] = str(BACKEND_TARGET)
    env.pop("RUSTFLAGS", None)
    env.pop("CARGO_ENCODED_RUSTFLAGS", None)
    env.pop("RUSTC_WRAPPER", None)
    env.pop("RUSTC_WORKSPACE_WRAPPER", None)
    return env


def _run(
    command: list[str], *, cwd: Path, env: dict[str, str], log: Path, label: str
) -> subprocess.CompletedProcess:
    log.parent.mkdir(parents=True, exist_ok=True)
    result = BUILD_LANE._run_logged(command, cwd=cwd, env=env, log=log)
    if result.returncode != 0:
        raise ProofError(f"{label} failed; inspect {log}")
    return result


def _require_toolchain():
    BUILD_LANE._require_host()
    rustup = BUILD_LANE._require_nightly()
    BUILD_LANE._cargo_wrapper(rustup)
    toolchain, _target = BUILD_LANE._toolchain()
    try:
        BUILD_LANE._llvm_ready(toolchain)
    except (InputError, OSError, ValueError) as error:
        raise ProofError(
            "the locked LLVM toolchain is missing; run `python3.14 "
            "rust-cpython/build.py fetch` first"
        ) from error
    return toolchain


def fetch() -> int:
    toolchain = _require_toolchain()
    _metadata, entry = _source_lock()
    blob = Cache(REPO / ".cache").fetch(entry)
    package = _extract_source(blob, fresh=True)
    command = [
        str(LANE / ".cargo-home" / "bin" / "cargo"),
        "fetch",
        "--locked",
        "--manifest-path",
        str(package / "Cargo.toml"),
    ]
    _run(
        command,
        cwd=package,
        env=_cargo_env(toolchain, offline=False, build_dir=BACKEND_TARGET),
        log=LOGS / "zlib-proof-cargo-fetch.log",
        label="zlib-rs dependency fetch",
    )
    print(f"OK    locked zlib-rs {entry.version} and Cargo dependencies are cached")
    return 0


def _makefile_value(path: Path, name: str) -> str:
    for line in path.read_text(errors="replace").splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() == name:
            return value.strip()
    raise ProofError(f"{path}: missing {name}")


def _run_smoke(python: Path, extension: Path, toolchain) -> dict[str, Any]:
    # Expected checksums from the matched C-zlib control for this fixed payload.
    code = (
        "import json,sys,zlib; "
        "data=(bytes(range(256))*4096)+b'zlib-rs proof'; "
        "assert zlib.__file__ == sys.argv[1], (zlib.__file__,sys.argv[1]); "
        f"assert zlib.ZLIB_RUNTIME_VERSION == {RUST_RUNTIME_VERSION!r}; "
        "packed=zlib.compress(data); assert zlib.decompress(packed)==data; "
        "stream=zlib.compressobj(); "
        "encoded=stream.compress(data[:12345])+stream.compress(data[12345:])+stream.flush(); "
        "decoder=zlib.decompressobj(); decoded=decoder.decompress(encoded)+decoder.flush(); "
        "assert decoded==data and decoder.eof; "
        "assert zlib.crc32(data)==1900127338; "
        "assert zlib.adler32(data)==2082438290; "
        "print(json.dumps({'module':zlib.__file__,'header_version':zlib.ZLIB_VERSION,"
        "'runtime_version':zlib.ZLIB_RUNTIME_VERSION,'roundtrip_bytes':len(data),"
        "'compressed_bytes':len(packed),'crc32':zlib.crc32(data),"
        "'adler32':zlib.adler32(data)}))"
    )
    env = BUILD_LANE._test_environment(toolchain)
    env["PYTHONPATH"] = str(OVERLAY)
    result = subprocess.run(
        [str(python), "-S", "-c", code, str(extension)],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ProofError(f"Rust zlib import/roundtrip smoke failed: {result.stderr.strip()}")
    try:
        return json.loads(result.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as error:
        raise ProofError("Rust zlib smoke did not emit its identity record") from error


def build() -> int:
    toolchain = _require_toolchain()
    source_metadata, entry = _source_lock()
    blob = Cache(REPO / ".cache").require(entry)
    package = _extract_source(blob, fresh=True)

    baseline = json.loads(CONTROL_REPORT.read_text())
    if baseline.get("status") != "built":
        raise ProofError(f"no-Rust CPython control is not built: {CONTROL_REPORT}")
    cpython_lock = json.loads((LANE / "sources.lock.json").read_text())["source"]
    if baseline.get("source", {}).get("commit") != cpython_lock["commit"]:
        raise ProofError("the no-Rust control does not match the pinned CPython source")
    makefile = CONTROL_BUILD / "Makefile"
    python = CONTROL_STAGE / "bin" / "python3.16"
    if not makefile.is_file() or not python.is_file():
        raise ProofError(
            "build the same-source control first with `python3.14 rust-cpython/build_no_rust.py`"
        )

    cargo = str(LANE / ".cargo-home" / "bin" / "cargo")
    _run(
        [
            cargo,
            "build",
            "--release",
            "--locked",
            "--offline",
            "--manifest-path",
            str(package / "Cargo.toml"),
        ],
        cwd=package,
        env=_cargo_env(toolchain, offline=True, build_dir=BACKEND_TARGET),
        log=LOGS / "zlib-proof-cargo-build.log",
        label="zlib-rs static library build",
    )

    static_library = BACKEND_TARGET / "release" / "libz_rs.a"
    if not static_library.is_file():
        raise ProofError(f"zlib-rs build did not produce {static_library}")
    BACKEND_LIB.mkdir(parents=True, exist_ok=True)
    zlib_link = BACKEND_LIB / "libz.a"
    if zlib_link.exists() or zlib_link.is_symlink():
        zlib_link.unlink()
    zlib_link.symlink_to(static_library)

    suffix = _makefile_value(makefile, "EXT_SUFFIX")
    target = f"Modules/zlib{suffix}"
    build_output = CONTROL_BUILD / target
    if not (CONTROL_BUILD / "Modules" / "zlibmodule.o").is_file():
        raise ProofError("the no-Rust CPython build lacks Modules/zlibmodule.o")
    OVERLAY.mkdir(parents=True, exist_ok=True)
    extension = OVERLAY / f"zlib{suffix}"
    original_backup: Path | None = None
    if build_output.exists():
        backup_dir = WORK / "backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        original_backup = backup_dir / build_output.name
        shutil.copy2(build_output, original_backup)
        build_output.unlink()
    try:
        make_env = BUILD_LANE._environment(
            toolchain, offline=True, build_dir=CONTROL_BUILD
        )
        _run(
            [
                str(toolchain.make),
                "-C",
                str(CONTROL_BUILD),
                target,
                f"MODULE_ZLIB_LDFLAGS=-L{BACKEND_LIB} -lz",
            ],
            cwd=REPO,
            env=make_env,
            log=LOGS / "zlib-proof-cpython-link.log",
            label="CPython zlib extension link against zlib-rs",
        )
        if not build_output.is_file():
            raise ProofError("CPython did not emit the zlib-rs-backed extension")
        shutil.copy2(build_output, extension)
    finally:
        if build_output.exists():
            build_output.unlink()
        if original_backup is not None:
            shutil.copy2(original_backup, build_output)

    otool = shutil.which("otool")
    llvm_nm = toolchain.llvm_prefix / "bin" / "llvm-nm"
    if otool is None or not llvm_nm.is_file():
        raise ProofError("otool and the locked LLVM llvm-nm are required for link validation")
    dependency_result = subprocess.run(
        [otool, "-L", str(extension)], capture_output=True, text=True, check=False
    )
    if dependency_result.returncode != 0:
        raise ProofError(f"otool failed to inspect {extension}")
    dependencies = dependency_result.stdout
    if any("libz" in line.lower() for line in dependencies.splitlines()[1:]):
        raise ProofError("zlib extension still dynamically links a libz library")
    symbols = subprocess.run(
        [str(llvm_nm), "-g", "--defined-only", str(extension)],
        capture_output=True,
        text=True,
        check=False,
    )
    if symbols.returncode != 0:
        raise ProofError(f"llvm-nm failed to inspect {extension}")
    for symbol in ("_zlibVersion", "_deflateInit2_", "_inflateInit2_"):
        if symbol not in symbols.stdout:
            raise ProofError(f"the linked extension does not define Rust zlib symbol {symbol}")

    smoke = _run_smoke(python, extension, toolchain)
    rustup = BUILD_LANE._require_nightly()
    cargo = str(LANE / ".cargo-home" / "bin" / "cargo")
    report = {
        "schema_version": 1,
        "status": "built",
        "source_cpython": {
            "repository": cpython_lock["repository"],
            "commit": cpython_lock["commit"],
            "version": cpython_lock["version"],
        },
        "backend": {
            "repository": source_metadata["repository"],
            "crate": source_metadata["crate"],
            "version": source_metadata["version"],
            "license": source_metadata["license"],
            "archive_sha256": entry.sha256,
            "cargo_lock_sha256": source_metadata["cargo_lock_sha256"],
            "static_library": str(static_library),
            "static_library_sha256": hashlib.sha256(static_library.read_bytes()).hexdigest(),
            "static_library_bytes": static_library.stat().st_size,
        },
        "toolchain": {
            "rust_channel": BUILD_LANE.RUST_CHANNEL,
            "rustc": BUILD_LANE._tool_output(
                [rustup, "run", BUILD_LANE.RUST_CHANNEL, "rustc", "-Vv"]
            ),
            "cargo": BUILD_LANE._tool_output([cargo, "-V"]),
            "llvm_clang": BUILD_LANE._tool_output(
                [str(toolchain.llvm_prefix / "bin" / "clang"), "--version"]
            ).splitlines()[0],
            "sdk": str(toolchain.sdkroot),
            "sdk_version": BUILD_LANE.sdk_version(toolchain.sdkroot),
            "deployment_target": toolchain.deployment_target,
            "cpu_baseline": toolchain.cpu_baseline,
        },
        "module": {
            "path": str(extension),
            "sha256": hashlib.sha256(extension.read_bytes()).hexdigest(),
            "runtime_identity": smoke,
            "dynamic_dependencies": [
                line.strip()
                for line in dependencies.splitlines()[1:]
                if line.strip()
            ],
            "static_zlib_symbols": ["zlibVersion", "deflateInit2_", "inflateInit2_"],
            "python_wrapper": "unchanged pinned CPython Modules/zlibmodule.c",
        },
        "tests": {"status": "not_run"},
    }
    BUILD_LANE._write_json(RESULT, report)
    print(
        f"OK    CPython {cpython_lock['version']} zlib module linked to "
        f"zlib-rs {entry.version} -> {extension}"
    )
    print(f"REPORT {RESULT}")
    return 0


def test() -> int:
    try:
        report = json.loads(RESULT.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ProofError(f"run the zlib proof build first: {error}") from error
    if report.get("status") != "built":
        raise ProofError("zlib proof build report is not complete")
    extension = Path(report.get("module", {}).get("path", ""))
    if not extension.is_file():
        raise ProofError("the zlib-rs extension recorded by the build is missing")
    extension_hash = hashlib.sha256(extension.read_bytes()).hexdigest()
    if extension_hash != report["module"].get("sha256"):
        raise ProofError("the zlib-rs extension changed after the proof build")
    toolchain = _require_toolchain()
    python = CONTROL_STAGE / "bin" / "python3.16"
    env = BUILD_LANE._test_environment(toolchain)
    env["PYTHONPATH"] = str(OVERLAY)
    command = [str(python), "-m", "test", *CPYTHON_TESTS]
    log = LOGS / "zlib-proof-cpython-tests.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w") as output:
        result = subprocess.run(
            command,
            cwd=REPO,
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
            check=False,
        )
    contents = log.read_text(errors="replace")
    match = re.search(r"Total tests: run=([\d,]+) skipped=([\d,]+)", contents)
    if result.returncode == 0 and match is None:
        raise ProofError(f"CPython test runner summary was not found in {log}")
    tests = {
        "status": "passed" if result.returncode == 0 else "failed",
        "files": list(CPYTHON_TESTS),
        "returncode": result.returncode,
        "run": int(match.group(1).replace(",", "")) if match else None,
        "skipped": int(match.group(2).replace(",", "")) if match else None,
        "log": str(log),
    }
    report["tests"] = tests
    report["status"] = "complete" if result.returncode == 0 else "failed"
    BUILD_LANE._write_json(RESULT, report)
    if result.returncode != 0:
        raise ProofError(f"CPython zlib consumer tests failed; inspect {log}")
    print(contents[-5000:])
    print(f"REPORT {RESULT}")
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("fetch", "build", "test"))
    args = parser.parse_args(argv)
    try:
        return {"fetch": fetch, "build": build, "test": test}[args.command]()
    except (
        BUILD_LANE.LaneError,
        BUILD_LANE.InputError,
        BUILD_LANE.BootstrapError,
        BUILD_LANE.SandboxError,
        ProofError,
        OSError,
        ValueError,
        KeyError,
    ) as error:
        print(f"FAIL  {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
