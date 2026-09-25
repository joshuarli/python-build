#!/usr/bin/env python3
"""Build the vanilla CPython ancestor as an isolated lane comparison control."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

LANE = Path(__file__).resolve().parent
REPO = LANE.parent
sys.path.insert(0, str(REPO))

from buildsys.bootstrap import problems as toolchain_problems  # noqa: E402
from buildsys.inputs import Cache, Input, InputError, load_lock, safe_extract  # noqa: E402
from buildsys.sandbox import SealedRun, SandboxError, available, network_boundary_selftest  # noqa: E402

sys.path.insert(0, str(LANE))
import lane_linux  # noqa: E402

_SPEC = importlib.util.spec_from_file_location("rust_cpython_build", LANE / "build.py")
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("cannot load the experiment's locked macOS toolchain helpers")
FORK = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = FORK
_SPEC.loader.exec_module(FORK)

LOCK = LANE / "upstream.sources.lock.json"
CACHE = REPO / ".cache"
WORK = LANE / "work" / "upstream-control"
SOURCE = WORK / "source"
BUILD = WORK / "build"
STAGE = WORK / "stage"
LOGS = LANE / "logs" / "upstream"
RESULTS = LANE / "results" / "upstream-build.json"
HOME = WORK / "home"
COMMIT = "0983642c966d9c536416101e99b7d2b085483847"
VERSION = "3.16.0a0"
LIBPYTHON = "libpython3.16.so.1.0" if FORK.IS_LINUX else "libpython3.16.dylib"
CONFIGURE_FLAGS = (
    "--enable-shared", "--with-lto=thin", "--enable-optimizations",
    "--enable-experimental-jit=no", "--with-tail-call-interp=no",
    "--without-ensurepip",
)


class ControlError(Exception):
    """The upstream control cannot safely match the pinned experiment."""


def source_input() -> Input:
    """Require a complete, single-purpose vanilla upstream source pin."""
    try:
        document = json.loads(LOCK.read_text())
        metadata = document["source"]
        entries = load_lock(LOCK)
    except (OSError, ValueError, KeyError, TypeError, InputError) as error:
        raise ControlError(f"invalid upstream source lock: {error}") from error
    if len(entries) != 1:
        raise ControlError("upstream source lock must contain exactly one input")
    item = entries[0]
    expected_url = f"https://codeload.github.com/python/cpython/tar.gz/{COMMIT}"
    if metadata != {
        "repository": "https://github.com/python/cpython",
        "commit": COMMIT,
        "version": VERSION,
        "license": "PSF-2.0",
        "fork_merge_base": COMMIT,
    } or (
        item.name != "cpython-upstream-control"
        or item.version != VERSION
        or item.url != expected_url
        or item.role != "test"
        or item.target not in FORK.LANE_TARGETS
        or item.license != "PSF-2.0"
        or item.size is None
    ):
        raise ControlError("upstream source lock disagrees with the selected merge base")
    return item


def _host_and_toolchain(*, require_ready: bool = True) -> tuple[Any, Any]:
    if FORK.IS_LINUX:
        toolchain, target = FORK._toolchain()
        if require_ready:
            problems = lane_linux.problems(toolchain)
            if problems:
                raise ControlError("locked Linux toolchain is unavailable: " + "; ".join(problems))
        return toolchain, target
    if platform.system() != "Darwin" or platform.machine().lower() not in {"arm64", "aarch64"}:
        raise ControlError("upstream control requires native Apple Silicon macOS or x86_64 Linux")
    toolchain, target = FORK._toolchain()
    if require_ready:
        problems = toolchain_problems(toolchain, host_floor="26.0")
        if problems:
            raise ControlError("locked macOS toolchain is unavailable: " + "; ".join(problems))
    return toolchain, target


def _source_root(extracted: Path) -> Path:
    children = [path for path in extracted.iterdir() if path.is_dir()]
    if len(children) != 1 or children[0].name != f"cpython-{COMMIT}":
        raise ControlError("upstream archive has an unexpected source root")
    source = children[0]
    for name in ("configure", "Lib", "Modules", "Include/patchlevel.h"):
        if not (source / name).exists():
            raise ControlError(f"upstream archive is missing {name}")
    header = (source / "Include/patchlevel.h").read_text()
    if not re.search(r'^#define PY_VERSION\s+"3\.16\.0a0"$', header, re.MULTILINE):
        raise ControlError("upstream source is not CPython 3.16.0a0")
    if (source / "Cargo.toml").exists():
        raise ControlError("upstream source unexpectedly contains a Cargo workspace")
    return source


def _extract_fresh(item: Input) -> Path:
    blob = Cache(CACHE).require(item)
    if SOURCE.exists():
        shutil.rmtree(SOURCE)
    return _source_root(safe_extract(blob, SOURCE))


def _environment(toolchain: Any, target: Any, jobs: int) -> dict[str, str]:
    if jobs < 1:
        raise ControlError("PGO workers must be positive")
    env = toolchain.toolchain().env()
    for name in tuple(env):
        if name.startswith(("CARGO_", "RUST", "BINDGEN_")) or name in (
            "HAVE_CARGO", "PY_CC", "PY_CFLAGS", "PYTHON_BUILD_DIR", "LLVM_TARGET",
        ):
            env.pop(name)
    env.update({
        "PATH": os.pathsep.join((str(toolchain.llvm_prefix / "bin"), "/usr/bin", "/bin", "/usr/sbin", "/sbin")),
        "HOME": str(HOME),
        "TMPDIR": str(WORK / "tmp"),
        **FORK._platform_flags(toolchain, target, STAGE),
        "PROFILE_TASK": FORK._profile_task(jobs),
        "LLVM_PROFDATA": str(toolchain.llvm_profdata),
        "PKG_CONFIG": str(toolchain.pkgconf),
        "SOURCE_DATE_EPOCH": FORK.SOURCE_DATE_EPOCH,
        "PYTHONHASHSEED": FORK.SOURCE_DATE_EPOCH,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPYCACHEPREFIX": str(WORK / "pycache"),
        "IPHONEOS_DEPLOYMENT_TARGET": "",
    })
    return env


def _require_configure_flags(source: Path) -> None:
    result = subprocess.run(
        [str(source / "configure"), "--help"], cwd=WORK,
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode:
        raise ControlError("upstream configure --help failed")
    help_text = result.stdout
    for flag in CONFIGURE_FLAGS:
        option = flag.split("=", 1)[0]
        if flag == "--without-ensurepip":
            option = "--with-ensurepip"
        if option not in help_text:
            raise ControlError(f"upstream configure does not advertise {flag}")


def _artifact_identity(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ControlError(f"upstream build is missing {path}")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": str(path), "size": path.stat().st_size,
            "sha256": digest.hexdigest()}


def fetch(*, source_only: bool = False) -> None:
    item = source_input()
    toolchain, _target = _host_and_toolchain(require_ready=False)
    blob, route = lane_linux.fetch_source(Cache(CACHE), item)
    print(f"OK    verified upstream source {item.sha256} ({route}) -> {blob}")
    if not source_only:
        FORK._fetch_llvm(toolchain)
        print(f"OK    locked LLVM {toolchain.llvm_version}")


def build(jobs: int | None = None) -> None:
    item = source_input()
    toolchain, target = _host_and_toolchain()
    FORK._llvm_ready(toolchain)
    if not FORK.IS_LINUX and not available():
        raise ControlError("offline build requires sandbox-exec")
    source = _extract_fresh(item)
    _require_configure_flags(source)
    for path in (BUILD, STAGE):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    worker_count = jobs if jobs is not None else max(1, (os.cpu_count() or 4) - 1)
    env = _environment(toolchain, target, worker_count)
    if FORK.IS_LINUX:
        sandbox = lane_linux.SealedRun(write_paths=[WORK, STAGE, LOGS, RESULTS.parent], home=HOME)
        proof = lane_linux.network_boundary_selftest(Path(sys.executable), WORK / "sandbox-probe")
        mechanism = lane_linux.describe()["mechanism"]
    else:
        sandbox = SealedRun(write_paths=[WORK, STAGE, LOGS, RESULTS.parent], home=HOME)
        proof = network_boundary_selftest(Path(sys.executable), WORK / "sandbox-probe")
        mechanism = "sandbox-exec deny network*"
    if not proof.get("ok"):
        raise ControlError(f"offline network boundary failed: {proof}")
    sealed_env = sandbox.environment(env)
    commands = (
        ("configure", [str(source / "configure"), f"--prefix={STAGE}", *CONFIGURE_FLAGS]),
        ("build", [str(toolchain.make), f"-j{worker_count}"]),
        ("install", [str(toolchain.make), "install"]),
    )
    for phase, command in commands:
        result = sandbox.run(command, cwd=BUILD, env=sealed_env, log=LOGS / f"{phase}.log")
        if result.returncode:
            raise ControlError(f"upstream {phase} failed; inspect {LOGS / phase}.log")
    python = STAGE / "bin" / "python3.16"
    if not python.is_file():
        raise ControlError("upstream install did not produce python3.16")
    identity_code = (
        "import json,sys,sysconfig; "
        "print(json.dumps({'version':sys.version.split()[0],"
        "'gil_disabled':sysconfig.get_config_var('Py_GIL_DISABLED'),"
        "'config_args':sysconfig.get_config_var('CONFIG_ARGS'),"
        "'cflags':sysconfig.get_config_var('CFLAGS'),"
        "'ldflags':sysconfig.get_config_var('LDFLAGS')}))"
    )
    identity_run = subprocess.run(
        [str(python), "-I", "-S", "-c", identity_code],
        cwd=STAGE, env=sealed_env, capture_output=True, text=True,
    )
    if identity_run.returncode:
        raise ControlError(f"upstream interpreter identity failed: {identity_run.stderr}")
    identity = json.loads(identity_run.stdout)
    if identity["version"] != VERSION or identity["gil_disabled"] in (1, "1"):
        raise ControlError("upstream interpreter version or GIL ABI disagrees with control")
    report = {
        "comparison_role": "vanilla upstream CPython 3.16 control",
        "source": {"repository": "https://github.com/python/cpython", "commit": COMMIT,
                   "version": VERSION, "archive_url": item.url,
                   "archive_sha256": item.sha256, "archive_size": item.size},
        "toolchain": toolchain.identity(),
        "configure_arguments": commands[0][1],
        "target": target.triple,
        "configure_environment": {name: sealed_env.get(name, "") for name in (
            "CC", "CXX", "AR", "RANLIB", "CFLAGS", "CXXFLAGS", "CPPFLAGS",
            "PY_CPPFLAGS", "LDFLAGS", "PROFILE_TASK", "LLVM_PROFDATA",
            "SDKROOT", "MACOSX_DEPLOYMENT_TARGET", "PKG_CONFIG", "PKG_CONFIG_PATH",
            "SOURCE_DATE_EPOCH", "PYTHONHASHSEED")},
        "pgo_workers": worker_count,
        "pgo_profile": _artifact_identity(BUILD / "code.profclangd"),
        "artifacts": {
            "python3.16": _artifact_identity(python),
            LIBPYTHON: _artifact_identity(STAGE / "lib" / LIBPYTHON),
        },
        "interpreter": identity,
        "executable": str(python),
        "offline_boundary": {"mechanism": mechanism, "selftest": proof},
        "logs": {phase: str(LOGS / f"{phase}.log") for phase, _ in commands},
    }
    RESULTS.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"OK    upstream CPython {VERSION} -> {STAGE}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    fetch_parser = sub.add_parser("fetch", help="verify and cache upstream source and locked LLVM")
    fetch_parser.add_argument("--source-only", action="store_true", help="cache only the upstream archive")
    build_parser = sub.add_parser("build", help="build the offline vanilla control")
    build_parser.add_argument("--pgo-jobs", type=int)
    sub.add_parser("doctor", help="check host, source cache and locked toolchain")
    args = parser.parse_args()
    if args.command == "fetch":
        fetch(source_only=args.source_only)
    elif args.command == "build":
        build(args.pgo_jobs)
    else:
        item = source_input()
        toolchain, target = _host_and_toolchain()
        print(json.dumps({"source_cached": lane_linux.fetch_source(Cache(CACHE), item)[1] == "cache",
                          "target": target.triple, "toolchain": toolchain.identity()}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ControlError, InputError, FORK.LaneError, SandboxError, OSError, ValueError) as error:
        print(f"FAIL  {error}", file=sys.stderr)
        raise SystemExit(1)
