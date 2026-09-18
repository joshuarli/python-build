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

SUPPORTED = {"x86_64-unknown-linux-musl"}


def _fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def _require_target(target: str) -> None:
    if target != SUPPORTED.copy().pop():
        _fail(f"target not implemented: {target} (supported: {sorted(SUPPORTED)})")


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
        "target": sorted(SUPPORTED)[0],
        "qualification": (
            "docker-buildkit" if _qualification_available() else "unavailable"
        ),
        "in_container": container,
    }
    for tool in ("clang", "ld.lld", "llvm-ar", "musl-gcc", "pkg-config"):
        report[tool] = shutil.which(tool)
    print(json.dumps(report, indent=2))
    return 0


def build(args: argparse.Namespace) -> int:
    _require_target(args.target)
    if args.sealed and not args.offline:
        _fail("--sealed requires --offline; qualification runs never touch the network")
    if args.offline and not args.sealed:
        print("offline development build is not qualification evidence; "
              "use --sealed for hermetic runs")
    if args.sealed:
        if not _qualification_available():
            _fail("sealed qualification requires the Dockerfile build stages; "
                  "docker/BuildKit is unavailable")
        _fail("sealed qualification is not implemented yet; "
              "M1c owns the offline rootfs build")
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
    fetch.add_argument("--target", default="x86_64-unknown-linux-musl")
    build_parser = commands.add_parser("build")
    build_parser.add_argument("--target", default="x86_64-unknown-linux-musl")
    build_parser.add_argument("--dev", action="store_true")
    build_parser.add_argument("--offline", action="store_true")
    build_parser.add_argument("--sealed", action="store_true")
    test = commands.add_parser("test")
    test.add_argument("--target", default="x86_64-unknown-linux-musl")
    compare = commands.add_parser("compare-reference")
    compare.add_argument("--target", default="x86_64-unknown-linux-musl")
    package = commands.add_parser("package")
    package.add_argument("--target", default="x86_64-unknown-linux-musl")
    reproduce = commands.add_parser("reproduce")
    reproduce.add_argument("--target", default="x86_64-unknown-linux-musl")
    args = parser.parse_args(argv)
    if args.command in {"fetch", "build", "test", "compare-reference",
                        "package", "reproduce"}:
        _require_target(args.target)
    if args.command == "doctor":
        return doctor()
    if args.command == "fetch":
        result = subprocess.run([sys.executable, "build/fetch.py"], cwd=Path(__file__).parent)
        return result.returncode
    if args.command == "build":
        return build(args)
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
        if not _qualification_available():
            _fail("reproduce needs two independent sealed Docker builds; "
                  "docker/BuildKit is unavailable")
        result = subprocess.run([sys.executable, "build/reproduce.py"], cwd=Path(__file__).parent)
        return result.returncode
    _fail(f"command not implemented: {args.command}")
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
