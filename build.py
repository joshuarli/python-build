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
        _fail(f"--target {target} does not match the running machine "
              f"({_NATIVE.triple}); this project builds natively per-arch "
              f"via `docker build --platform {TARGETS[target].docker_platform}`, "
              f"it does not cross-compile")


def _qualification_available() -> bool:
    """Sealed runs execute in Dockerfile-defined stages, not on the host."""
    if not shutil.which("docker"):
        return False
    probe = subprocess.run(
        ["docker", "buildx", "version"], capture_output=True, timeout=30
    )
    return probe.returncode == 0


def doctor() -> int:
    container = Path("/.dockerenv").is_file()
    report = {
        "host": platform.machine(),
        "python": sys.version.split()[0],
        "native_target": _NATIVE.triple if _NATIVE else None,
        "supported_targets": sorted(SUPPORTED),
        "qualification": (
            "docker-buildkit" if _qualification_available() else "unavailable"
        ),
        "in_container": container,
    }
    for tool in ("clang", "ld.lld", "llvm-ar", "patchelf", "pkg-config"):
        report[tool] = shutil.which(tool)
    print(json.dumps(report, indent=2))
    return 0


def build(args: argparse.Namespace) -> int:
    _require_native_target(args.target)
    if args.sealed and not args.offline:
        _fail("--sealed requires --offline; qualification runs never touch the network")
    if args.offline and not args.sealed:
        print("offline development build is not qualification evidence; "
              "use --sealed for hermetic runs")
    if args.sealed:
        if not _qualification_available():
            _fail("sealed qualification requires the Dockerfile build stages; "
                  "docker/BuildKit is unavailable")
        _fail("sealed qualification is not implemented as a build.py subcommand; "
              "use `docker build --platform <platform> --target sealed .` "
              "(M1c owns the offline rootfs build; see Dockerfile)")
    result = subprocess.run(
        [sys.executable, "build/deps.py"], cwd=Path(__file__).parent
    )
    if result.returncode != 0:
        return result.returncode
    return subprocess.run(
        [sys.executable, "build/cpython.py"], cwd=Path(__file__).parent
    ).returncode


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
    test = commands.add_parser("test")
    test.add_argument("--target", default=DEFAULT_TARGET)
    compare = commands.add_parser("compare-reference")
    compare.add_argument("--target", default=DEFAULT_TARGET)
    package = commands.add_parser("package")
    package.add_argument("--target", default=DEFAULT_TARGET)
    reproduce = commands.add_parser("reproduce")
    reproduce.add_argument("--target", default=DEFAULT_TARGET)
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
            _fail("reproduce needs two independent sealed Docker builds; "
                  "docker/BuildKit is unavailable")
        result = subprocess.run(
            [sys.executable, "build/reproduce.py", "--target", args.target],
            cwd=Path(__file__).parent,
        )
        return result.returncode
    _fail(f"command not implemented: {args.command}")
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
