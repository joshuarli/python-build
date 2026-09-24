#!/usr/bin/env python3
"""Build a same-source CPython control without the Rust _base64 module."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any

LANE = Path(__file__).resolve().parent
REPO = LANE.parent
sys.path.insert(0, str(REPO))

_BUILD_SPEC = importlib.util.spec_from_file_location(
    "rust_cpython_build", LANE / "build.py"
)
if _BUILD_SPEC is None or _BUILD_SPEC.loader is None:
    raise RuntimeError("cannot load the Rust-for-CPython build helpers")
BUILD_LANE = importlib.util.module_from_spec(_BUILD_SPEC)
sys.modules[_BUILD_SPEC.name] = BUILD_LANE
_BUILD_SPEC.loader.exec_module(BUILD_LANE)

WORK = LANE / "work"
SOURCE_DIR = WORK / "source-no-rust"
BUILD_DIR = WORK / "build-no-rust"
STAGE = LANE / "stage-no-rust"
LOGS = LANE / "logs" / "no-rust"
REPORT = LANE / "results" / "no-rust-build.json"


def _configuration(toolchain: Any, target: Any, jobs: int) -> tuple[list[str], dict[str, str]]:
    cflags = " ".join((
        "-O3", target.cpu_baseline_cflag, "-fPIC",
        f"-mmacosx-version-min={toolchain.deployment_target}",
    ))
    linkflags = f"-mmacosx-version-min={toolchain.deployment_target}"
    arguments = [
        f"--prefix={STAGE}",
        "--enable-shared",
        "--with-lto=thin",
        "--enable-optimizations",
        "--enable-experimental-jit=no",
        "--with-tail-call-interp=no",
        "--without-ensurepip",
    ]
    environment = BUILD_LANE._environment(
        toolchain, offline=True, build_dir=BUILD_DIR
    )
    environment.update({
        "CFLAGS": cflags,
        "CXXFLAGS": cflags,
        "CPPFLAGS": f"-isysroot {toolchain.sdkroot}",
        "PY_CPPFLAGS": f"-isysroot {toolchain.sdkroot}",
        "LDFLAGS": linkflags,
        "PROFILE_TASK": BUILD_LANE._profile_task(jobs),
        "LLVM_PROFDATA": str(toolchain.llvm_profdata),
        "PKG_CONFIG_PATH": BUILD_LANE._brew_pkg_config_path(),
        # This fork's generated configure script otherwise defaults HAVE_CARGO
        # to yes when Cargo is absent from PATH.
        "HAVE_CARGO": "no",
        "ac_cv_prog_HAVE_CARGO": "no",
        "PATH": os.pathsep.join((
            str(toolchain.llvm_prefix / "bin"),
            "/usr/bin", "/bin", "/usr/sbin", "/sbin",
        )),
    })
    for name in (
        "CARGO_HOME", "CARGO_NET_OFFLINE", "CARGO_TARGET_DIR", "RUSTUP_TOOLCHAIN",
        "RUST_SHARED_BUILD", "LLVM_TARGET", "BINDGEN_EXTRA_CLANG_ARGS",
    ):
        environment.pop(name, None)
    return arguments, environment


def _build_python() -> Path:
    makefile = BUILD_DIR / "Makefile"
    values: dict[str, str] = {}
    for line in makefile.read_text(errors="replace").splitlines():
        name, separator, value = line.partition("=")
        if separator and name in {"BUILDPYTHON", "BUILDEXE"}:
            values[name] = value.strip()
    name = values.get("BUILDPYTHON", "").replace(
        "$(BUILDEXE)", values.get("BUILDEXE", "")
    )
    if not name or "$" in name or Path(name).name != name:
        raise BUILD_LANE.LaneError(f"cannot resolve control interpreter name {name!r}")
    return BUILD_DIR / name


def _run(arguments: list[str], *, cwd: Path, env: dict[str, str], log: Path, sandbox) -> None:
    result = BUILD_LANE._require_command(
        arguments, cwd=cwd, env=env, log=log, sealed=sandbox
    )
    if result.returncode != 0:
        raise BUILD_LANE.LaneError(f"control build failed; inspect {log}")


def main() -> int:
    BUILD_LANE._require_host()
    doctor = BUILD_LANE.doctor_report()
    if not doctor["ok"]:
        raise BUILD_LANE.LaneError("doctor found prerequisites missing; run fetch first")
    toolchain, target = BUILD_LANE._toolchain()
    BUILD_LANE._llvm_ready(toolchain)
    source = BUILD_LANE._extract_fresh(SOURCE_DIR)
    jobs = max(1, (os.cpu_count() or 4) - 1)

    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    if STAGE.exists():
        shutil.rmtree(STAGE)
    BUILD_DIR.mkdir(parents=True)
    STAGE.mkdir(parents=True)
    LOGS.mkdir(parents=True, exist_ok=True)

    arguments, environment = _configuration(toolchain, target, jobs)
    if shutil.which("cargo", path=environment["PATH"]) is not None:
        raise BUILD_LANE.LaneError("Cargo remains on PATH in the no-Rust control environment")
    sandbox = BUILD_LANE._macos_sandbox()
    environment = sandbox.environment(environment)
    configure = [str(source / "configure"), *arguments]
    _run(
        configure,
        cwd=BUILD_DIR,
        env=environment,
        log=LOGS / "configure.log",
        sandbox=sandbox,
    )
    configure_cache = (BUILD_DIR / "config.log").read_text(errors="replace")
    if "HAVE_CARGO='no'" not in configure_cache:
        raise BUILD_LANE.LaneError(
            "configure did not honor HAVE_CARGO=no; refusing to build a Rust control"
        )
    if "MODULE__BASE64_STATE='yes'" in configure_cache:
        raise BUILD_LANE.LaneError(
            "configure enabled the Rust _base64 module in the no-Rust control"
        )
    make = [str(toolchain.make), f"-j{jobs}"]
    _run(make, cwd=BUILD_DIR, env=environment, log=LOGS / "build.log", sandbox=sandbox)
    _run(
        [str(toolchain.make), "install"],
        cwd=BUILD_DIR,
        env=environment,
        log=LOGS / "install.log",
        sandbox=sandbox,
    )

    python = STAGE / "bin" / "python3.16"
    if not python.is_file():
        raise BUILD_LANE.LaneError(f"control install did not produce {python}")
    code = (
        "import base64,binascii,importlib.util,json,sys,sysconfig; "
        "data=bytes(range(256))*4096; "
        "assert importlib.util.find_spec('_base64') is None; "
        "assert base64.b64encode(data)==binascii.b2a_base64(data,newline=False); "
        "print(json.dumps({'implementation':sys.implementation.name,'version':sys.version,"
        "'config_args':sysconfig.get_config_var('CONFIG_ARGS'),"
        "'cflags':sysconfig.get_config_var('CFLAGS'),"
        "'extension_suffix':sysconfig.get_config_var('EXT_SUFFIX'),"
        "'rust_base64_module':'absent','public_base64_matches_binascii':True}))"
    )
    result = BUILD_LANE._run_logged(
        [str(python), "-I", "-S", "-c", code],
        cwd=STAGE,
        env=BUILD_LANE._test_environment(toolchain),
        log=LOGS / "identity.log",
    )
    if result.returncode != 0:
        raise BUILD_LANE.LaneError(f"control interpreter validation failed; inspect {LOGS / 'identity.log'}")
    identity = json.loads((LOGS / "identity.log").read_text().strip().splitlines()[-1])
    if identity["implementation"] != "cpython" or identity["version"].split()[0] != "3.16.0a0":
        raise BUILD_LANE.LaneError("control interpreter identity does not match the pinned CPython fork")
    if "HAVE_CARGO=no" not in (BUILD_DIR / "Makefile").read_text(errors="replace"):
        configure_log = (LOGS / "configure.log").read_text(errors="replace")
        if "Could not find the cargo executable" not in configure_log:
            raise BUILD_LANE.LaneError("configure unexpectedly detected Cargo in the no-Rust control")

    cargo_hash = hashlib.sha256((source / "Cargo.lock").read_bytes()).hexdigest()
    report = {
        "status": "built",
        "comparison_role": "same-source control without Rust _base64",
        "source": {
            "repository": doctor["source"]["repository"],
            "commit": doctor["source"]["commit"],
            "version": doctor["source"]["version"],
            "archive_sha256": doctor["source"]["archive_sha256"],
            "cargo_lock_sha256": cargo_hash,
        },
        "interpreter": identity,
        "executable": str(python),
        "c_toolchain": toolchain.identity(),
        "configure_arguments": configure,
        "configure_environment": {
            key: environment.get(key, "")
            for key in (
                "CC", "CFLAGS", "CXXFLAGS", "CPPFLAGS", "LDFLAGS", "PROFILE_TASK",
                "LLVM_PROFDATA", "MACOSX_DEPLOYMENT_TARGET", "PKG_CONFIG_PATH",
            )
        },
        "cargo_detected": False,
        "logs": {"configure": str(LOGS / "configure.log"),
                 "build": str(LOGS / "build.log"), "install": str(LOGS / "install.log")},
    }
    BUILD_LANE._write_json(REPORT, report)
    print(f"OK    no-Rust CPython {identity['version'].split()[0]} -> {STAGE}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BUILD_LANE.LaneError, BUILD_LANE.InputError, BUILD_LANE.BootstrapError,
            BUILD_LANE.SandboxError, OSError, ValueError, KeyError) as error:
        print(f"FAIL  {error}", file=sys.stderr)
        raise SystemExit(1)
