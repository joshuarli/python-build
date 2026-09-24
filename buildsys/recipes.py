"""Dependency recipes, shared by the Linux/musl and macOS targets.

Each recipe builds into its own scratch directory and installs into a shared
private prefix (plan 5.2). Static PIC libraries keep downstream linkage simple;
the dependency closure is small enough that a plain list beats a scheduler.

The build systems invoked here are the components' own — autotools, plain
make, and OpenSSL's Configure. Only the toolchain, the flags, and which
packages are built at all differ per family; that data lives on `Toolchain`
and in `buildsys.deporder`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path

from .targets import native_target

REPO = Path(__file__).resolve().parent.parent


class BuildError(Exception):
    """A dependency or interpreter build step failed."""


@dataclass
class Toolchain:
    """The compiler/linker set a recipe is built with.

    `family` selects the environment conventions that genuinely differ: the
    Linux/musl toolchain is addressed by bare names that the container's PATH
    resolves and pins its linker explicitly, while the macOS toolchain is
    addressed by absolute paths in the verified LLVM prefix and deliberately
    leaves the linker to the clang driver, which supplies the libLTO matching the compiler's own
    bitcode generation (plan Section 5.1).
    """

    cc: str = "clang"
    cxx: str = "clang++"
    ar: str = "llvm-ar"
    ranlib: str = "llvm-ranlib"
    ld: str = "ld.lld"
    nm: str = "llvm-nm"
    strip: str = "llvm-strip"
    make: str = "make"
    lto: str = "-flto=thin"
    jobs: int = max(1, (os.cpu_count() or 4))
    pkg_config_path: str = ""
    family: str = "linux-musl"
    sdkroot: str = ""  # macOS
    deployment_target: str = ""  # macOS
    cpu_baseline: str = ""  # e.g. -march=x86-64, -mcpu=apple-m1

    @property
    def is_macos(self) -> bool:
        return self.family == "macos"

    def env(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        env = dict(os.environ)
        # Scrub influences that could contaminate the build (plan 7). The
        # DYLD_* family is macOS's equivalent of LD_PRELOAD/LD_LIBRARY_PATH:
        # an inherited value would substitute a different library at link or
        # run time without any change to the recipe.
        for var in ("PYTHONPATH", "PYTHONHOME", "CPATH", "C_INCLUDE_PATH",
                    "LIBRARY_PATH", "LD_LIBRARY_PATH", "LD_PRELOAD",
                    "DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH",
                    "DYLD_INSERT_LIBRARIES", "DYLD_FRAMEWORK_PATH"):
            env.pop(var, None)
        env.update(
            {
                "CC": self.cc,
                "CXX": self.cxx,
                "AR": self.ar,
                "RANLIB": self.ranlib,
                "NM": self.nm,
                "STRIP": self.strip,
            }
        )
        if self.is_macos:
            # The linker is intentionally not named: clang's driver selects
            # the platform linker and passes the libLTO matching its own
            # bitcode. Pinning LD to a separately installed LLD is how you
            # get a version-mismatched bitcode rejection (Section 5.1).
            env.pop("LD", None)
            if self.sdkroot:
                env["SDKROOT"] = self.sdkroot
            if self.deployment_target:
                # Autotools configure scripts read this directly; clang also
                # honours it. CFLAGS/LDFLAGS carry -mmacosx-version-min too,
                # because a component that forks its own compile line must
                # not fall back to the SDK's (newer) default floor.
                env["MACOSX_DEPLOYMENT_TARGET"] = self.deployment_target
        else:
            env["LD"] = self.ld
        if self.pkg_config_path:
            # Dependency detection must not find unrelated host packages
            # (plan 5.2): the private prefix is the only search root.
            env["PKG_CONFIG_PATH"] = self.pkg_config_path
            env["PKG_CONFIG_SYSROOT_DIR"] = ""
            if self.is_macos:
                # PKG_CONFIG_PATH only *prepends*; Homebrew's own
                # /opt/homebrew/lib/pkgconfig stays on the default search
                # path and carries .pc files for openssl, sqlite, libffi and
                # the rest at different versions. PKG_CONFIG_LIBDIR replaces
                # the default path outright. The frozen Linux container has
                # no competing prefix, so it keeps its original behavior.
                env["PKG_CONFIG_LIBDIR"] = self.pkg_config_path
        else:
            env.pop("PKG_CONFIG_PATH", None)
            if self.is_macos:
                env.pop("PKG_CONFIG_LIBDIR", None)
        if extra:
            env.update(extra)
        return env

    def cflags(self, extra: str = "") -> str:
        parts = ["-O3", self.cpu_baseline, "-fno-omit-frame-pointer", "-fPIC"]
        if self.is_macos:
            parts.append(f"-mmacosx-version-min={self.deployment_target}")
        else:
            parts.append("-fstack-protector-strong")
            parts.append("-D_FORTIFY_SOURCE=2")
        if extra:
            parts.append(extra)
        return " ".join(p for p in parts if p)

    def ldflags(self, prefix: Path, extra: str = "") -> str:
        parts = [f"-L{prefix}/lib"]
        if self.is_macos:
            parts.append(f"-mmacosx-version-min={self.deployment_target}")
        else:
            # macOS has no equivalent of these; they are ELF loader
            # hardening and ELF build-id, not portable flags (Section 5.3).
            parts += ["-Wl,-z,noexecstack", "-Wl,--build-id=sha1"]
        if extra:
            parts.append(extra)
        return " ".join(p for p in parts if p)


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


def build_recipe(
    recipe: Recipe,
    blob: Path,
    work: Path,
    prefix: Path,
    *,
    toolchain: Toolchain | None = None,
) -> None:
    """Extract a verified blob and build it into the private prefix.

    `toolchain` is injected by drivers that target macOS; when omitted the
    Linux/musl default is used, which is what the frozen container recipes
    rely on.
    """
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
    pkg_config_path = (
        f"{prefix}/lib/pkgconfig:{prefix}/share/pkgconfig"
        if (prefix / "lib/pkgconfig").exists() or (prefix / "share/pkgconfig").exists()
        else ""
    )
    if toolchain is None:
        toolchain = Toolchain(pkg_config_path=pkg_config_path)
    elif not toolchain.pkg_config_path:
        toolchain = replace(toolchain, pkg_config_path=pkg_config_path)
    if recipe.install == "make":
        # Plain make packages: no configure step at all. CFLAGS/LDFLAGS are
        # passed as make command-line overrides because some Makefiles
        # (bzip2) assign these variables internally and ignore the
        # environment. Make's command line wins over any in-makefile
        # assignment. `-D_FILE_OFFSET_BITS=64` is a large-file concern for
        # 32-bit-off_t platforms and is not needed on Darwin.
        env = toolchain.env()
        makefile = _find_makefile(source)
        if toolchain.is_macos:
            make_cflags = toolchain.cflags(recipe.cflags)
            make_ldflags = toolchain.ldflags(prefix, recipe.ldflags)
        else:
            # Verbatim reproduction of the frozen Linux flag strings. See the
            # freeze note in plan Section 1.2: these recipes already produced
            # validated artifacts with exactly this text, and "improving" it
            # here would alter a completed target without re-validating it.
            # `-D_FILE_OFFSET_BITS=64` is a large-file concern for
            # 32-bit-off_t platforms and is not needed on Darwin.
            make_cflags = f"{recipe.cflags} -O3 -fPIC -D_FILE_OFFSET_BITS=64"
            make_ldflags = recipe.ldflags
        command = [
            toolchain.make,
            "-j",
            str(toolchain.jobs),
            f"CFLAGS={make_cflags}",
            f"LDFLAGS={make_ldflags}",
        ]
        # bzip2's Makefile assigns `CC=gcc` and zstd's defaults to `cc`. A
        # makefile assignment beats the environment, so exporting CC in `env`
        # is not enough — the dependency would be compiled by whatever the
        # makefile names rather than by the toolchain the target declares.
        # Command-line variable assignments are the only form that wins.
        # This applies on every family: a recipe that silently uses an
        # unlisted compiler produces an artifact nobody can attribute, and on
        # macOS it also breaks LTO, since Apple clang's bitcode generation
        # does not match the LLVM the lock pins.
        command += [
            f"CC={toolchain.cc}",
            f"CXX={toolchain.cxx}",
            f"AR={toolchain.ar}",
            f"RANLIB={toolchain.ranlib}",
        ]
        command += list(recipe.make_targets)
        run(command, cwd=makefile.parent, env=env, log=recipe.log_path / "make.log")
    elif recipe.install == "autotools":
        if toolchain.is_macos:
            cflags = toolchain.cflags(recipe.cflags)
            cxxflags = toolchain.cflags(recipe.cxxflags)
            ldflags = toolchain.ldflags(prefix, recipe.ldflags)
        else:
            cflags = f"{recipe.cflags} -O3 -fPIC"
            cxxflags = f"{recipe.cxxflags} -O3 -fPIC"
            ldflags = recipe.ldflags
        env = toolchain.env(
            {"CFLAGS": cflags, "CXXFLAGS": cxxflags, "LDFLAGS": ldflags}
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
            [toolchain.make, "-j", str(toolchain.jobs), *recipe.make_targets],
            cwd=build_directory,
            env=env,
            log=recipe.log_path / "make.log",
        )
        run(
            [toolchain.make, "install"],
            cwd=build_directory,
            env=env,
            log=recipe.log_path / "install.log",
        )
    elif recipe.install == "openssl":
        target = native_target()
        if toolchain.is_macos:
            openssl_cflags = (
                f"-O3 -fPIC {toolchain.cpu_baseline} -fno-omit-frame-pointer "
                f"-mmacosx-version-min={toolchain.deployment_target}"
            )
            # OpenSSL honours MACOSX_DEPLOYMENT_TARGET for its own compile
            # lines, but its generated link line is not guaranteed to carry
            # the flag, so it is given explicitly as well.
            openssl_ldflags = toolchain.ldflags(prefix)
        else:
            openssl_cflags = f"-O3 -fPIC {target.cpu_baseline_cflag} -fno-omit-frame-pointer"
            openssl_ldflags = "-fuse-ld=lld -Wl,-z,noexecstack"
        env = toolchain.env({"CFLAGS": openssl_cflags, "LDFLAGS": openssl_ldflags})
        run(["perl", str(source / "Configure"), target.openssl_configure_target,
             f"--prefix={prefix}", "--libdir=lib", "--openssldir=/etc/ssl",
             "no-shared", "no-module", *recipe.configure_args],
            cwd=source, env=env, log=recipe.log_path / "configure.log")
        run([toolchain.make, "-j", str(toolchain.jobs), "build_sw"], cwd=source,
            env=env, log=recipe.log_path / "make.log")
        run([toolchain.make, "install_sw"], cwd=source,
            env=env, log=recipe.log_path / "install.log")
    else:
        raise BuildError(f"unknown install style {recipe.install!r}")
