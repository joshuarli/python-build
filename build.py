"""Typed controller front door for the M1 distribution build.

The CLI validates arguments and delegates to buildsys; heavy work lives in
buildsys and per-phase drivers. Unsupported targets fail closed: no artifacts
are created for a target that has no implemented native executor (plan 3).
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parent))
from buildsys.targets import TARGETS, UnsupportedTargetError, native_target  # noqa: E402

SUPPORTED = set(TARGETS)
try:
    _NATIVE = native_target()
except UnsupportedTargetError:
    _NATIVE = None
# `doctor` reports whatever this host/container actually is, even if
# unsupported; every other command needs --target to name a SUPPORTED
# triple explicitly, so this default is a convenience, not a fallback that
# papers over an unsupported machine.
DEFAULT_TARGET = _NATIVE.triple if _NATIVE else "x86_64-unknown-linux-musl"

# Commands that run compiled recipes/the interpreter itself: these are never
# cross-compiled (plan Section 12), so the requested --target must be the
# architecture this process is actually running as right now.
NATIVE_EXECUTION_COMMANDS = {"build", "test", "compare-reference", "package"}


def _fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def _require_target(target: str) -> None:
    if target not in SUPPORTED:
        _fail(f"target not implemented: {target} (supported: {sorted(SUPPORTED)})")


def _require_native_target(target: str) -> None:
    _require_target(target)
    if _NATIVE is None:
        _fail(f"this machine ({platform.machine()}) has no target description; "
              f"run inside a container built for one of {sorted(SUPPORTED)}")
    if target != _NATIVE.triple:
        if _NATIVE.is_macos:
            _fail(f"--target {target} does not match the running machine "
                  f"({_NATIVE.triple}); the macOS target builds and runs "
                  f"natively on Apple Silicon, it does not cross-compile")
        _fail(f"--target {target} does not match the running machine "
              f"({_NATIVE.triple}); this project builds natively per-arch "
              f"via `docker build --platform {TARGETS[target].docker_platform}`, "
              f"it does not cross-compile")


def _positive_int(value: str) -> int:
    try:
        result = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if result < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return result


SANDBOX_EXEC = "/usr/bin/sandbox-exec"


def _qualification_available(target=None) -> bool:
    """Sealed runs execute under a platform-appropriate isolation mechanism.

    Linux targets use Dockerfile-defined BuildKit stages; macOS cannot build
    or run Mach-O binaries in a Linux container, so it uses a `sandbox-exec`
    profile with `(deny network*)` instead (plan Section 7). Neither is
    assumed to work — each is probed.
    """
    target = target or _NATIVE
    if target is not None and target.is_macos:
        return Path(SANDBOX_EXEC).is_file()
    if not shutil.which("docker"):
        return False
    probe = subprocess.run(
        ["docker", "buildx", "version"], capture_output=True, timeout=30
    )
    return probe.returncode == 0


def _macos_report(report: dict) -> None:
    """Host, SDK, and toolchain facts the macOS build depends on (plan 3, 5.1)."""
    import plistlib

    from buildsys.bootstrap import (
        BootstrapError,
        linker_identity,
        load_macos_toolchain,
        problems,
        sdk_version,
    )

    report["macos"] = {"product_version": platform.mac_ver()[0]}
    sdk = subprocess.run(
        ["xcrun", "--show-sdk-path"], capture_output=True, text=True
    ).stdout.strip()
    report["macos"]["sdk_path"] = sdk or None
    report["macos"]["sdk_version"] = sdk_version(Path(sdk)) if sdk else None
    report["macos"]["linker"] = linker_identity()
    report["macos"]["sandbox_exec"] = SANDBOX_EXEC if Path(SANDBOX_EXEC).is_file() else None
    report["macos"]["codesign"] = shutil.which("codesign")
    lock = Path(__file__).resolve().parent / "bootstrap.lock.json"
    try:
        locked = load_macos_toolchain(lock)
    except BootstrapError as error:
        report["macos"]["toolchain_lock"] = {"ok": False, "error": str(error)}
        return
    found = problems(locked, host_floor=locked.deployment_target)
    report["macos"]["toolchain_lock"] = {
        "ok": not found,
        "llvm_version": locked.llvm_version,
        "deployment_target": locked.deployment_target,
        "cpu_baseline": locked.cpu_baseline,
        "problems": found,
    }
    clang = locked.llvm_prefix / "bin" / "clang"
    report["macos"]["clang"] = str(clang) if clang.is_file() else None
    report["macos"]["clang_reported"] = (
        subprocess.run([str(clang), "--version"], capture_output=True, text=True)
        .stdout.splitlines()[0] if clang.is_file() else None
    )
    profdata = locked.llvm_profdata
    report["macos"]["llvm_profdata"] = (
        str(profdata) if profdata.is_file() else None
    )
    report["macos"]["llvm_profdata_reported"] = (
        subprocess.run([str(profdata), "--version"], capture_output=True, text=True)
        .stdout.splitlines()[0] if profdata.is_file() else None
    )


def doctor() -> int:
    container = Path("/.dockerenv").is_file()
    report = {
        "host": platform.machine(),
        "platform": platform.system(),
        "python": sys.version.split()[0],
        "native_target": _NATIVE.triple if _NATIVE else None,
        "native_family": _NATIVE.family if _NATIVE else None,
        "supported_targets": sorted(SUPPORTED),
        "qualification": (
            "unavailable"
            if not _qualification_available()
            else ("sandbox-exec" if _NATIVE and _NATIVE.is_macos else "docker-buildkit")
        ),
        "in_container": container,
    }
    if _NATIVE is not None and _NATIVE.is_macos:
        _macos_report(report)
    else:
        for tool in ("clang", "ld.lld", "llvm-ar", "patchelf", "pkg-config"):
            report[tool] = shutil.which(tool)
    print(json.dumps(report, indent=2))
    return 0


def build(args: argparse.Namespace) -> int:
    _require_native_target(args.target)
    if args.pgo_jobs is not None and not _NATIVE.is_macos:
        _fail("--pgo-jobs is only supported for the macOS PGO build")
    if args.sealed and not args.offline:
        _fail("--sealed requires --offline; qualification runs never touch the network")
    if args.offline and not args.sealed:
        print("offline development build is not qualification evidence; "
              "use --sealed for hermetic runs")
    if args.sealed:
        if not _qualification_available():
            _fail(
                "sealed qualification requires "
                + ("the sandbox-exec profile runner"
                   if _NATIVE and _NATIVE.is_macos
                   else "the Dockerfile build stages")
                + "; the isolation mechanism is unavailable"
            )
        _fail(
            "sealed qualification is not implemented as a build.py subcommand; "
            + ("use the sandbox-exec sealed runner " if _NATIVE and _NATIVE.is_macos
               else "use `docker build --platform <platform> --target sealed .` ")
            + "(M1c owns the offline build; see plan Section 7)"
        )
    result = subprocess.run(
        [sys.executable, "build/deps.py"], cwd=Path(__file__).parent
    )
    if result.returncode != 0:
        return result.returncode
    cpython_command = [sys.executable, "build/cpython.py"]
    if args.pgo_jobs is not None:
        cpython_command.extend(["--pgo-jobs", str(args.pgo_jobs)])
    return subprocess.run(cpython_command, cwd=Path(__file__).parent).returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="build.py")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    fetch = commands.add_parser("fetch")
    fetch.add_argument("--target", default=DEFAULT_TARGET)
    build_parser = commands.add_parser("build")
    build_parser.add_argument("--target", default=DEFAULT_TARGET)
    build_parser.add_argument("--dev", action="store_true")
    build_parser.add_argument("--offline", action="store_true")
    build_parser.add_argument("--sealed", action="store_true")
    build_parser.add_argument(
        "--pgo-jobs", type=_positive_int,
        help="number of workers for macOS CPython's --pgo training task "
             "(default: CPython compile jobs, one fewer than host CPUs)",
    )
    test = commands.add_parser("test")
    test.add_argument("--target", default=DEFAULT_TARGET)
    compare = commands.add_parser("compare-reference")
    compare.add_argument("--target", default=DEFAULT_TARGET)
    package = commands.add_parser("package")
    package.add_argument("--target", default=DEFAULT_TARGET)
    reproduce = commands.add_parser("reproduce")
    reproduce.add_argument("--target", default=DEFAULT_TARGET)
    reproduce.add_argument(
        "--pgo-jobs", type=_positive_int,
        help="reuse this worker count for each clean macOS PGO build",
    )
    args = parser.parse_args(argv)
    if args.command == "doctor":
        return doctor()
    if args.command == "fetch":
        _require_target(args.target)
        result = subprocess.run([sys.executable, "build/fetch.py"], cwd=Path(__file__).parent)
        return result.returncode
    if args.command == "build":
        return build(args)
    if args.command in NATIVE_EXECUTION_COMMANDS - {"build"}:
        _require_native_target(args.target)
    if args.command == "test":
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
            cwd=Path(__file__).parent,
        )
        return result.returncode
    if args.command == "compare-reference":
        result = subprocess.run(
            [sys.executable, "build/package.py", "--compare-only"], cwd=Path(__file__).parent
        )
        return result.returncode
    if args.command == "package":
        result = subprocess.run([sys.executable, "build/package.py"], cwd=Path(__file__).parent)
        return result.returncode
    if args.command == "reproduce":
        _require_target(args.target)
        if not _qualification_available():
            isolation = (
                "sandbox-exec" if _NATIVE and _NATIVE.is_macos
                else "Docker BuildKit"
            )
            _fail(f"reproduce needs the target's sealed build isolation; {isolation} is unavailable")
        result = subprocess.run(
            [sys.executable, "build/reproduce.py", "--target", args.target]
            + (["--pgo-jobs", str(args.pgo_jobs)] if args.pgo_jobs is not None else []),
            cwd=Path(__file__).parent,
        )
        return result.returncode
    _fail(f"command not implemented: {args.command}")
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
