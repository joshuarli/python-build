"""Dependency recipes for the M1 musl x86_64 distribution.

Each recipe builds into its own scratch directory and installs into a shared
private prefix (plan 5.2). Static PIC libraries keep downstream linkage simple;
the dependency closure is small enough that a plain list beats a scheduler.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


class BuildError(Exception):
    """A dependency or interpreter build step failed."""


@dataclass
class Toolchain:
    cc: str = "clang"
    cxx: str = "clang++"
    ar: str = "llvm-ar"
    ranlib: str = "llvm-ranlib"
    ld: str = "ld.lld"
    nm: str = "llvm-nm"
    strip: str = "llvm-strip"
    lto: str = "-flto=thin"
    jobs: int = max(1, (os.cpu_count() or 4))
    pkg_config_path: str = ""

    def env(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        env = dict(os.environ)
        # Scrub influences that could contaminate the build (plan 7).
        for var in ("PYTHONPATH", "PYTHONHOME", "CPATH", "C_INCLUDE_PATH",
                    "LIBRARY_PATH", "LD_LIBRARY_PATH", "LD_PRELOAD"):
            env.pop(var, None)
        env.update(
            {
                "CC": self.cc,
                "CXX": self.cxx,
                "AR": self.ar,
                "RANLIB": self.ranlib,
                "NM": self.nm,
                "STRIP": self.strip,
                "LD": self.ld,
            }
        )
        if self.pkg_config_path:
            # Dependency detection must not find unrelated host packages
            # (plan 5.2): the private prefix is the only search root.
            env["PKG_CONFIG_PATH"] = self.pkg_config_path
            env["PKG_CONFIG_SYSROOT_DIR"] = ""
        else:
            env.pop("PKG_CONFIG_PATH", None)
        if extra:
            env.update(extra)
        return env


def run(cmd: list[str], *, cwd: Path, env: dict[str, str], log: Path) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w") as handle:
        result = subprocess.run(
            cmd, cwd=cwd, env=env, stdout=handle, stderr=subprocess.STDOUT
        )
    if result.returncode != 0:
        raise BuildError(f"command failed ({result.returncode}): {cmd} — log {log}")


def _find_makefile(source: Path) -> Path:
    """Return the package's Makefile, tolerating one level of nesting."""
    direct = source / "Makefile"
    if direct.is_file():
        return direct
    for child in sorted(source.iterdir()):
        candidate = child / "Makefile"
        if candidate.is_file():
            return candidate
    raise BuildError(f"no Makefile found under {source}")


def _find_configure(source: Path) -> Path:
    """Return the package's configure script, tolerating one level of nesting."""
    direct = source / "configure"
    if direct.is_file():
        return direct
    for child in sorted(source.iterdir()):
        candidate = child / "configure"
        if candidate.is_file():
            return candidate
    raise BuildError(f"no configure script found under {source}")


@dataclass
class Recipe:
    name: str
    extract_dir: str
    source_subdir: str = ""
    build_subdir: str = ""
    configure_args: tuple[str, ...] = ()
    make_targets: tuple[str, ...] = ()
    cflags: str = ""
    cxxflags: str = ""
    ldflags: str = ""
    install: str = "autotools"
    log_path: Path | None = None


def build_recipe(recipe: Recipe, blob: Path, work: Path, prefix: Path) -> None:
    """Extract a verified blob and build it into the private prefix."""
    # Resolve everything up front: a relative executable path would be
    # resolved against the child process's cwd, not the parent's.
    work = Path(work).resolve()
    prefix = Path(prefix).resolve()
    blob = Path(blob).resolve()
    if recipe.log_path is not None:
        recipe.log_path = Path(recipe.log_path).resolve()
    scratch = work / recipe.name
    if scratch.exists():
        raise BuildError(f"{scratch} already exists; refusing to reuse scratch tree")
    sys.path.insert(0, str(REPO))
    from buildsys.inputs import safe_extract

    safe_extract(blob, scratch)
    source = scratch / recipe.source_subdir if recipe.source_subdir else scratch
    toolchain = Toolchain(
        pkg_config_path=(
            f"{prefix}/lib/pkgconfig:{prefix}/share/pkgconfig"
            if (prefix / "lib/pkgconfig").exists() or (prefix / "share/pkgconfig").exists()
            else ""
        )
    )
    if recipe.install == "make":
        # Plain make packages: no configure step at all. CFLAGS/LDFLAGS are
        # passed as make command-line overrides because some Makefiles
        # (bzip2) assign these variables internally and ignore the
        # environment. Make's command line wins over any in-makefile
        # assignment.
        env = toolchain.env()
        makefile = _find_makefile(source)
        run(
            [
                "make",
                "-j",
                str(toolchain.jobs),
                f"CFLAGS={recipe.cflags} -O3 -fPIC -D_FILE_OFFSET_BITS=64",
                f"LDFLAGS={recipe.ldflags}",
                *recipe.make_targets,
            ],
            cwd=makefile.parent,
            env=env,
            log=recipe.log_path / "make.log",
        )
    elif recipe.install == "autotools":
        env = toolchain.env(
            {
                "CFLAGS": f"{recipe.cflags} -O3 -fPIC",
                "CXXFLAGS": f"{recipe.cxxflags} -O3 -fPIC",
                "LDFLAGS": recipe.ldflags,
            }
        )
        configure = _find_configure(source)
        build_directory = scratch / recipe.build_subdir if recipe.build_subdir else configure.parent
        build_directory.mkdir(parents=True, exist_ok=True)
        run(
            [str(configure), f"--prefix={prefix}", *recipe.configure_args],
            cwd=build_directory,
            env=env,
            log=recipe.log_path / "configure.log",
        )
        run(
            ["make", "-j", str(toolchain.jobs), *recipe.make_targets],
            cwd=build_directory,
            env=env,
            log=recipe.log_path / "make.log",
        )
        run(
            ["make", "install"],
            cwd=build_directory,
            env=env,
            log=recipe.log_path / "install.log",
        )
    elif recipe.install == "openssl":
        env = toolchain.env({"CFLAGS": "-O3 -fPIC -march=x86-64 -fno-omit-frame-pointer",
                             "LDFLAGS": "-fuse-ld=lld -Wl,-z,noexecstack"})
        run(["perl", str(source / "Configure"), "linux-x86_64",
             f"--prefix={prefix}", "--libdir=lib", "--openssldir=/etc/ssl",
             "no-shared", "no-module", *recipe.configure_args],
            cwd=source, env=env, log=recipe.log_path / "configure.log")
        run(["make", "-j", str(toolchain.jobs), "build_sw"], cwd=source,
            env=env, log=recipe.log_path / "make.log")
        run(["make", "install_sw"], cwd=source,
            env=env, log=recipe.log_path / "install.log")
    else:
        raise BuildError(f"unknown install style {recipe.install!r}")
