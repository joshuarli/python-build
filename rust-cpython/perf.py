#!/usr/bin/env python3
"""Fast-iteration performance builds for the Rust-for-CPython lane.

Builds matched optimized interpreters without PGO or ThinLTO so a
baseline/candidate pair can be rebuilt quickly. The only deliberate
difference between a pair is the source overlay: an empty overlay for the
pristine-fork control, the full committed overlay for the Rust candidate.

All outputs live under isolated `work/perf/<name>/`, `stage-perf-<name>/`,
and `perf-<name>-*` log/report names. The coverage `work/build`, `stage`,
and `results/build.json` trees are never read or removed here.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

LANE = Path(__file__).resolve().parent


def _lane_build():
    spec = importlib.util.spec_from_file_location("lane_build", LANE / "build.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the lane coverage builder")
    module = importlib.util.module_from_spec(spec)
    sys.modules["lane_build"] = module
    spec.loader.exec_module(module)
    return module


lb = _lane_build()
LaneError = lb.LaneError


def _check_name(name: str) -> str:
    if re.fullmatch(r"[a-z0-9][a-z0-9-]*", name) is None:
        raise LaneError(f"perf build name must match [a-z0-9][a-z0-9-]*: {name!r}")
    return name


def _tag(name: str) -> str:
    return name if name.startswith("perf-") else f"perf-{name}"


def _paths(name: str) -> dict[str, Path]:
    tag = _tag(name)
    work = lb.WORK / "perf" / tag
    return {
        "work": work,
        "source_parent": work / "source",
        "build": work / "build",
        "stage": LANE / f"stage-{tag}",
        "configure_log": lb.LOGS / f"{tag}-configure.log",
        "build_log": lb.LOGS / f"{tag}-build.log",
        "install_log": lb.LOGS / f"{tag}-install.log",
        "cargo_log": lb.LOGS / f"{tag}-cargo-offline-check.log",
        "report": lb.RESULTS / f"{tag}.json",
    }


def _perf_flags(toolchain, target) -> dict[str, str]:
    # Fast iteration over maximum optimization: -O2 instead of -O3, no
    # debug info, no link-time optimization. Profile-guided optimization
    # is off by construction: configure never receives
    # --enable-optimizations. Test modules stay enabled so a perf build
    # can still run focused CPython suites and the full suite for
    # correctness; dropping them would save build time but remove that
    # check. Cargo stays on the release profile: a dev profile would
    # punish the Rust routes artificially and is not a performance result.
    flags = " ".join(("-O2", target.cpu_baseline_cflag, "-fPIC",
                      f"-mmacosx-version-min={toolchain.deployment_target}"))
    return {
        "CFLAGS": flags,
        "CXXFLAGS": flags,
        "CPPFLAGS": f"-isysroot {toolchain.sdkroot}",
        "PY_CPPFLAGS": f"-isysroot {toolchain.sdkroot}",
        "LDFLAGS": f"-mmacosx-version-min={toolchain.deployment_target}",
        "PKG_CONFIG_PATH": lb._brew_pkg_config_path(),
    }


def _overlay_members() -> set[str]:
    members: set[str] = set()
    for manifest in lb.OVERLAY.glob("Modules/_*/Cargo.toml"):
        package = tomllib.loads(manifest.read_text()).get("package", {})
        name = package.get("name") if isinstance(package, dict) else None
        if not isinstance(name, str) or not name:
            raise LaneError(f"overlay Rust module has no package name: {manifest}")
        members.add(name)
    return members


def _built_members(build_log: Path, members: set[str]) -> list[str]:
    pattern = re.compile(r"(?:Compiling|Fresh) ([^ ]+) v[^ ]+")
    found: set[str] = set()
    for line in build_log.read_text(errors="replace").splitlines():
        match = pattern.search(line)
        if match and match.group(1) in members:
            found.add(match.group(1))
    return sorted(found)


def _build_python(build_dir: Path) -> Path:
    makefile = build_dir / "Makefile"
    if not makefile.is_file():
        raise LaneError(f"configured build Makefile is missing: {makefile}")
    name = lb._make_value(makefile, "BUILDPYTHON")
    suffix = lb._make_value(makefile, "BUILDEXE")
    name = name.replace("$(BUILDEXE)", suffix)
    if not name or "$" in name or Path(name).name != name:
        raise LaneError(f"cannot resolve CPython build interpreter name {name!r}")
    return build_dir / name


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def doctor() -> int:
    try:
        report = lb.doctor_report()
    except Exception as error:
        print(json.dumps({"ok": False, "problems": [str(error)]}, indent=2))
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


def build(*, name: str, empty_overlay: bool, jobs: int | None = None) -> int:
    _check_name(name)
    if lb.IS_LINUX:
        raise LaneError("perf builds currently support only native Apple Silicon macOS")
    if jobs is not None and jobs < 1:
        raise LaneError("build jobs must be positive")
    if not lb.doctor_report()["ok"]:
        raise LaneError("doctor found prerequisites missing; run `build.py doctor` for details")
    paths = _paths(name)
    toolchain, target = lb._toolchain()
    lb._llvm_ready(toolchain)
    source = lb._extract_fresh(paths["source_parent"])
    if empty_overlay:
        overlay = {"files": 0, "sha256": None, "pristine": True}
    else:
        overlay = lb._apply_overlay(source)
    env = lb._environment(toolchain, offline=True, build_dir=paths["build"])
    lb._require_command(
        [str(lb.CARGO_HOME / "bin" / "cargo"), "fetch", "--locked", "--offline",
         "--manifest-path", str(source / "Cargo.toml")],
        cwd=source, env=env, log=paths["cargo_log"],
    )
    for path in (paths["build"], paths["stage"]):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)
    args = [
        f"--prefix={paths['stage']}",
        "--enable-shared",
        "--enable-experimental-jit=no",
        "--with-tail-call-interp=no",
        "--without-ensurepip",
    ]
    env.update(_perf_flags(toolchain, target))
    env.update({
        "PY_CC": str(toolchain.llvm_prefix / "bin" / "clang"),
        "PY_CPPFLAGS": env["CPPFLAGS"],
        "PY_CFLAGS": env["CFLAGS"],
        "PYTHON_BUILD_DIR": str(paths["build"]),
        "CARGO_BUILD_JOBS": str(jobs if jobs is not None else max(1, (os.cpu_count() or 4) - 1)),
        lb._cargo_linker_variable(): str(toolchain.llvm_prefix / "bin" / "clang"),
        "IPHONEOS_DEPLOYMENT_TARGET": "",
    })
    sandbox = lb._sealed_sandbox()
    env = sandbox.environment(env)
    configure = [str(source / "configure"), *args]
    lb._require_command(configure, cwd=paths["build"], env=env,
                        log=paths["configure_log"], sealed=sandbox)
    setup_local = source / "Modules" / "Setup.local"
    if setup_local.is_file():
        build_setup_local = paths["build"] / "Modules" / "Setup.local"
        build_setup_local.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(setup_local, build_setup_local)
    workers = jobs if jobs is not None else max(1, (os.cpu_count() or 4) - 1)
    # Configure ties the Cargo profile to its own PGO flag, so a no-PGO
    # build defaults to dev. The release profile is selected here on the
    # make command line instead: command-line variables override the
    # Makefile defaults, and both profile and target directory move
    # together so artifact paths stay coherent. No source file changes.
    make = [str(toolchain.make), f"-j{workers}",
            "CARGO_PROFILE=release", "CARGO_TARGET_DIR=release"]
    lb._require_command(make, cwd=paths["build"], env=env,
                        log=paths["build_log"], sealed=sandbox)
    if "--profile release" not in paths["build_log"].read_text(errors="replace"):
        raise LaneError("perf build did not invoke cargo with --profile release")
    lb._require_command([str(toolchain.make), "install"], cwd=paths["build"], env=env,
                        log=paths["install_log"], sealed=sandbox)
    python = paths["stage"] / "bin" / "python3.16"
    if not python.is_file():
        raise LaneError(f"perf install did not produce {python}")
    cargo_profile = lb._make_value(paths["build"] / "Makefile", "CARGO_PROFILE")
    if cargo_profile != "dev":
        raise LaneError(f"unexpected configured Cargo default {cargo_profile!r}; expected 'dev'")
    cargo_profile = "release"
    cargo_env = dict(env)
    cargo_env.update({
        "CARGO_TARGET_DIR": str(paths["build"] / "target"),
        "LLVM_TARGET": lb.TARGET,
        "RUST_SHARED_BUILD": "1",
    })
    members = set(lb._workspace_members(source, cargo_env))
    required = {"_base64", "cpython-sys"} | (set() if empty_overlay else _overlay_members())
    if not required <= members:
        raise LaneError("perf workspace is missing members: "
                        + ", ".join(sorted(required - members)))
    built = set(_built_members(paths["build_log"], members))
    missing = required - built
    if missing:
        raise LaneError("perf build did not compile Rust members: " + ", ".join(sorted(missing)))
    module = lb._module_report(paths["stage"], python, toolchain)
    metadata, source_input = lb._read_lock()
    _write_json(paths["report"], {
        "status": "built",
        "build_mode": "perf-no-pgo-no-lto",
        "name": name,
        "pristine": empty_overlay,
        "target": lb.TARGET,
        "source_commit": metadata["commit"],
        "source_archive_sha256": source_input.sha256,
        "overlay": overlay,
        "cargo_lock_sha256": hashlib.sha256((source / "Cargo.lock").read_bytes()).hexdigest(),
        "configure_arguments": configure,
        "cflags": env["CFLAGS"],
        "cargo_profile": cargo_profile,
        "cargo_profile_selected_by": "make command-line override "
            "(configure defaults to dev without its PGO flag)",
        "pgo": False,
        "lto": False,
        "interpreter": module,
        "build_interpreter": str(_build_python(paths["build"])),
        "rust": lb._rust_identity(shutil.which("rustup")),
        "c_toolchain": toolchain.identity(),
        "stage": str(paths["stage"]),
    })
    print(f"OK    perf CPython {module['version'].split()[0]} -> {paths['stage']}")
    return 0


def test(*, name: str, suites: list[str], all_suites: bool = False,
          jobs: int | None = None) -> int:
    # Module focus (--suite test_zlib) and full-suite (--all) correctness
    # checks for a perf build. Suites run unsealed like the coverage
    # runner: measurement isolation belongs to the benchmark passes, not
    # to correctness suites.
    _check_name(name)
    if all_suites == bool(suites):
        raise LaneError("select --all or at least one --suite, but not both")
    if any(re.fullmatch(r"test_[a-z0-9_]+", suite) is None for suite in suites):
        raise LaneError("suite names must be CPython test modules or packages named test_*")
    if jobs is not None and jobs < 1:
        raise LaneError("test jobs must be positive")
    paths = _paths(name)
    if not paths["report"].is_file():
        raise LaneError(f"no completed perf build named {name!r}; run perf.py build first")
    report = json.loads(paths["report"].read_text())
    if report.get("status") not in {"built", "suite-failed", "suite-passed",
                                    "all-failed", "all-passed"}:
        raise LaneError(f"perf report does not describe a completed build: {paths['report']}")
    build_python = _build_python(paths["build"])
    if not build_python.is_file():
        raise LaneError(f"perf build interpreter is missing: {build_python}")
    toolchain, _target = lb._toolchain()
    env = lb._test_environment(toolchain)
    scope = "all" if all_suites else "suite"
    label = "all" if all_suites else "-".join(suites)
    if len(label) > 160:
        label = f"{'-'.join(suites[:3])}-{hashlib.sha256(label.encode()).hexdigest()[:16]}"
    log = lb.LOGS / f"{_tag(name)}-{label}.log"
    workers = jobs if jobs is not None else lb._test_jobs()
    result = lb._run_python_test(
        [str(build_python), "-m", "test", "-j", str(workers), "--timeout=900", *suites],
        cwd=paths["build"], env=env, log=log,
    )
    report["tests"] = {"scope": scope, "suites": suites, **result}
    report["status"] = f"{scope}-passed" if result["returncode"] == 0 else f"{scope}-failed"
    _write_json(paths["report"], report)
    if result["returncode"] != 0:
        raise LaneError(f"CPython suite failed; inspect {log}")
    print("OK    default-resource CPython suite" if all_suites
          else f"OK    CPython suites: {', '.join(suites)}")
    return 0


def clean(*, name: str | None = None) -> int:
    if name is not None:
        _check_name(name)
        paths = _paths(name)
        for key in ("work", "stage"):
            if paths[key].exists():
                shutil.rmtree(paths[key])
        for key in ("configure_log", "build_log", "install_log", "cargo_log", "report"):
            if paths[key].is_file():
                paths[key].unlink()
        print(f"OK    removed perf outputs for {name}")
        return 0
    perf_work = lb.WORK / "perf"
    if perf_work.exists():
        shutil.rmtree(perf_work)
    for path in LANE.glob("stage-perf-*"):
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
    for path in lb.LOGS.glob("perf-*"):
        if path.is_file():
            path.unlink()
    for path in lb.RESULTS.glob("perf-*"):
        if path.is_file():
            path.unlink()
    print("OK    removed all perf outputs (coverage trees untouched)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rust-for-CPython fast-iteration perf builds")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="report host and locked input readiness")
    build_parser = commands.add_parser("build", help="build an optimized no-PGO no-LTO interpreter")
    build_parser.add_argument("--name", required=True, help="isolated build name, e.g. perf-upstream")
    build_parser.add_argument("--empty-overlay", action="store_true",
                              help="build the pristine fork without the Rust overlay")
    build_parser.add_argument("--jobs", type=int, metavar="N", help="parallel build jobs")
    test_parser = commands.add_parser("test", help="run CPython suites on a perf build")
    test_parser.add_argument("--name", required=True, help="isolated build name to test")
    test_parser.add_argument("--all", action="store_true", help="run all default-resource CPython tests")
    test_parser.add_argument("--jobs", type=int, metavar="N", help="parallel test workers")
    test_parser.add_argument("--suite", action="append", default=[], metavar="TEST_NAME",
                             help="complete CPython test module or package; repeatable")
    clean_parser = commands.add_parser("clean", help="remove perf outputs only")
    clean_parser.add_argument("--name", default=None, help="isolated build name; omit for all perf outputs")
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            return doctor()
        if args.command == "build":
            return build(name=args.name, empty_overlay=args.empty_overlay, jobs=args.jobs)
        if args.command == "test":
            return test(name=args.name, suites=args.suite, all_suites=args.all, jobs=args.jobs)
        return clean(name=args.name)
    except (LaneError, lb.InputError, lb.BootstrapError, lb.SandboxError,
            OSError, ValueError) as error:
        print(f"FAIL  {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
