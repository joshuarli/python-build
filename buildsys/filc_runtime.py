"""Relocate a Fil-C install with its musl/Pizfix loader and runtime.

Fil-C's loader can open an ELF named on its command line. A static syscall
launcher resolves its own prefix and invokes that loader directly, preserving
arbitrary environment keys and symlink-specific path configuration. The
kernel never needs a prefix-specific PT_INTERP path. Keep `libyoloc.so` byte
for byte from the verified toolchain: adding an rpath to that loader made it
segfault before the first system call in the relocation smoke.
"""

from __future__ import annotations

import ast
import json
import pprint
import shutil
import subprocess
from pathlib import Path

from .relocate import (
    RelocationError, clean_sysconfig, find_elfs, fix_script_shebangs,
    set_relative_rpath, strip_private_prefix,
)
from .targets import Target


FILC_RUNTIME_LIBRARIES = ("libc.so", "libpizlo.so", "libyoloc.so")
_INERT_INTERPRETER = "/proc/self/fd/255"


def _patchelf(*args: str, patchelf: str) -> None:
    result = subprocess.run([patchelf, *args], capture_output=True, text=True)
    if result.returncode:
        raise RelocationError(f"patchelf {args}: {result.stderr.strip()}")


def _build_launcher(binary: Path, loader_name: str) -> None:
    """Install a libc-free x86_64 entrypoint; the payload remains Fil-C/musl."""
    source = Path(__file__).with_name("filc_launcher.c")
    result = subprocess.run(
        ["cc", "-Os", "-nostdlib", "-static", "-no-pie", "-fno-stack-protector",
         "-fno-builtin", "-Wl,-z,noexecstack",
         f'-DFILC_LOADER_NAME="{loader_name}"', str(source), "-o", str(binary)],
        capture_output=True, text=True,
    )
    if result.returncode:
        raise RelocationError(f"Fil-C launcher compilation failed: {result.stderr[-1000:]}")


def clean_filc_metadata(install: Path, private_prefix: Path, pizfix: Path) -> None:
    """Remove builder paths from all shipped Fil-C compiler metadata.

    Consumers must select a Fil-C compiler explicitly. `filc-clang` is a
    deliberate unresolved command name until they provide the pinned
    toolchain; falling back to an ordinary `clang` would claim a false ABI.
    """
    repo = private_prefix.parent.parent
    source = repo / "build/work/cpython/Python-3.14.6"
    build = repo / "build/work/cpython-build"
    filc_bin = pizfix.parent / "build/bin"

    def clean(value: str, *, config_args: bool = False) -> str:
        value = value.replace(str(filc_bin / "clang++"), "filc-clang++")
        value = value.replace(str(filc_bin / "clang"), "filc-clang")
        if config_args:
            for path, label in (
                (private_prefix, "<private-dependencies>"),
                (source, "<build-source>"),
                (build, "<build-directory>"),
            ):
                value = value.replace(str(path), label)
        else:
            for path in (private_prefix, source, build):
                value = strip_private_prefix(value, path)
        if str(repo) in value:
            raise RelocationError(f"Fil-C metadata retains a build path: {value[:120]}")
        return value

    lib = install / "lib/python3.14"
    for path in lib.glob("_sysconfigdata_*.py"):
        document = ast.parse(path.read_text())
        assignment = next((item for item in document.body if isinstance(item, ast.Assign)
                           and any(isinstance(target, ast.Name) and target.id == "build_time_vars"
                                   for target in item.targets)), None)
        if assignment is None:
            raise RelocationError(f"Fil-C sysconfigdata has no build_time_vars: {path}")
        values = ast.literal_eval(assignment.value)
        if not isinstance(values, dict):
            raise RelocationError(f"Fil-C sysconfigdata is not a mapping: {path}")
        for key, value in values.items():
            if isinstance(value, str):
                values[key] = clean(value, config_args=key == "CONFIG_ARGS")
        path.write_text("# Fil-C consumer configuration; build paths removed.\n"
                        "build_time_vars = " + pprint.pformat(values, sort_dicts=True) + "\n")
        cache = path.parent / "__pycache__"
        if cache.is_dir():
            for compiled in cache.glob(f"{path.stem}.*.pyc"):
                compiled.unlink()

    for path in lib.glob("_sysconfig_vars_*.json"):
        values = json.loads(path.read_text())
        if not isinstance(values, dict):
            raise RelocationError(f"Fil-C sysconfig vars are not a mapping: {path}")
        for key, value in values.items():
            if isinstance(value, str):
                values[key] = clean(value, config_args=key == "CONFIG_ARGS")
        path.write_text(json.dumps(values, indent=2, sort_keys=True) + "\n")

    for path in lib.rglob("Makefile"):
        lines = path.read_text().splitlines(keepends=True)
        path.write_text("".join(clean(line, config_args=line.startswith("CONFIG_ARGS="))
                                for line in lines))

    # A .pc file must derive its prefix from its own location after a move.
    for path in (install / "lib/pkgconfig").glob("python-3.14*.pc"):
        original = path.read_text()
        if "prefix=/install\n" not in original:
            raise RelocationError(f"Fil-C pkg-config prefix is unexpected: {path}")
        path.write_text(original.replace("prefix=/install\n", "prefix=${pcfiledir}/../..\n", 1))


def relocate_filc(
    install: Path,
    private_prefix: Path,
    pizfix: Path,
    target: Target,
    *,
    patchelf: str = "patchelf",
) -> list[Path]:
    """Bundle the exact Fil-C runtime and make the installed Python movable."""
    if not target.is_filc or Path(target.musl_loader).name != target.musl_loader:
        raise RelocationError("Fil-C relocation needs a Fil-C target and loader basename")
    install = Path(install)
    runtime = Path(pizfix) / "lib"
    lib_dir = install / "lib"
    binary = install / "bin" / "python3.14"
    if not binary.is_file() or binary.is_symlink():
        raise RelocationError(f"Fil-C interpreter missing: {binary}")
    for name in (*FILC_RUNTIME_LIBRARIES, target.musl_loader):
        source = runtime / name
        if not source.exists():
            raise RelocationError(f"Fil-C runtime member missing: {source}")
        destination = lib_dir / name
        if destination.exists() or destination.is_symlink():
            raise RelocationError(f"Fil-C runtime member conflicts with install: {destination}")
        if source.is_symlink():
            destination.symlink_to(source.readlink())
        else:
            shutil.copy2(source, destination)

    touched: list[Path] = []
    for elf in find_elfs(install):
        if elf.name == "libyoloc.so" and elf.parent == lib_dir:
            continue
        set_relative_rpath(elf, lib_dir, patchelf=patchelf)
        touched.append(elf)

    # The real ELF is only an argument to the bundled loader. A direct exec
    # must fail closed instead of using the Pizfix path embedded by clang.
    _patchelf("--set-interpreter", _INERT_INTERPRETER, str(binary), patchelf=patchelf)
    real_binary = binary.with_name("python3.14.real")
    if real_binary.exists():
        raise RelocationError(f"Fil-C real interpreter already exists: {real_binary}")
    binary.rename(real_binary)
    _build_launcher(binary, target.musl_loader)

    clean_sysconfig(install, private_prefix)
    clean_filc_metadata(install, private_prefix, pizfix)
    fix_script_shebangs(install)
    return touched
