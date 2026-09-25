"""Build all locked dependencies into the private prefix.

One driver serves both families. What differs per family is data — the
dependency set, the toolchain, and a handful of configure arguments — not
control flow: the recipes themselves are the same autotools/make/OpenSSL
build systems CPython and its libraries already ship.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from buildsys.bootstrap import BootstrapError, lto_smoke_test, toolchain_for  # noqa: E402
from buildsys.deporder import dependency_order  # noqa: E402
from buildsys.inputs import Cache, InputError, load_lock  # noqa: E402
from buildsys.recipes import BuildError, Recipe, build_recipe  # noqa: E402
from buildsys.targets import Target, UnsupportedTargetError, native_target  # noqa: E402

# Extract-directory names as they appear inside each tarball.
EXTRACT_DIRS = {
    "zlib": "zlib-1.3.1",
    "bzip2": "bzip2-1.0.8",
    "xz": "xz-5.8.1",
    "zstd": "cpython-source-deps-zstd-1.5.7",  # cpython-source-deps export layout checked below
    "expat": "expat-2.8.1",
    "mpdecimal": "mpdecimal-4.0.0",
    "libffi": "libffi-3.8.0",
    "libedit": "libedit-20240808-3.1",
    "ncurses": "ncurses-6.5",
    "libuuid": "libuuid-1.0.3",
    "bdb": "db-6.0.19",
    "sqlite": "sqlite-autoconf-3530100",
    "openssl": "openssl-3.5.7",
}

# Packages whose build Makefile lives below the tarball root.
SOURCE_SUBDIRS = {
    "zstd": "cpython-source-deps-zstd-1.5.7/lib",
    "bdb": "db-6.0.19/dist",  # BDB keeps configure in dist/
    "openssl": "openssl-3.5.7",
}

PREFIX_CPPFLAGS = "-I{prefix}/include"
PREFIX_LDFLAGS = "-L{prefix}/lib"


def configure_args(name: str, prefix: Path | None = None, target: Target | None = None) -> tuple[str, ...]:
    if name not in EXTRACT_DIRS:
        raise BuildError(f"unsupported dependency: {name}")
    target = target or native_target()
    # Resolve the private prefix from the driver's own location, not the
    # process cwd: builds run from /work inside the container.
    resolved = (prefix if prefix is not None else REPO / "build" / "prefix").resolve()
    if name not in dependency_order(target):
        raise BuildError(f"{name} is not a {target.family} build input")
    # Static PIC libraries keep downstream linkage simple on both families
    # Neither family has a use for shared dependency libraries.
    if name == "openssl":
        return ()  # the Configure target string carries the platform choice
    if target.is_macos:
        # The macOS set has no package needing a bespoke argument: bzip2 and
        # zstd are plain-make recipes, and the rest take the generic pair.
        return ("--disable-shared", "--enable-static")
    if name == "zlib":
        return ("--static",)
    if name in {"xz", "ncurses", "libffi", "sqlite"}:
        return ("--disable-shared", "--enable-static")
    if name == "bdb":
        # CPython's _dbm module (with --with-dbmliborder=bdb:...) links
        # dbm_open(), which db.h redefines to __db_ndbm_open() only when
        # BDB is built with its historic ndbm-compatibility interface.
        return ("--disable-shared", "--enable-static", "--enable-dbm")
    if name == "libedit":
        # libedit's configure probes -lncurses/-lcurses/-ltermcap/-ltinfo in
        # turn and needs ncurses headers on the include path. The private
        # prefix ships the wide build under include/ncursesw, so alias the
        # library to an unversioned -lncurses name and expose the headers.
        # Alpine-only: macOS links the platform's own libedit.
        lib = resolved / "lib"
        inc = resolved / "include"
        alias = lib / "libncurses.so"
        if not alias.exists():
            os.symlink("libncursesw.a", alias)
        return (
            "--disable-shared",
            "--enable-static",
            f"LDFLAGS=-L{lib}",
            f"CPPFLAGS=-I{inc} -I{inc}/ncursesw",
        )
    return ("--disable-shared", "--enable-static")


def install_style(name: str) -> str:
    """Packages without autotools configure: bzip2, zstd."""
    if name in {"bzip2", "zstd"}:
        return "make"
    if name == "openssl":
        return "openssl"
    return "autotools"

def cflags_for(name: str, target: Target | None = None) -> str:
    """Per-package CFLAGS additions."""
    target = target or native_target()
    if name == "sqlite":
        # Match the supported SQLite extension profile exercised by the
        # python-build-standalone distribution tests. Keep these as compile
        # definitions on SQLite itself; the CPython configure switch below
        # controls the separate sqlite3 extension-loading wrapper.
        return " ".join((
            "-DSQLITE_ENABLE_FTS3",
            "-DSQLITE_ENABLE_FTS3_PARENTHESIS",
            "-DSQLITE_ENABLE_FTS4",
            "-DSQLITE_ENABLE_FTS5",
            "-DSQLITE_ENABLE_GEOPOLY",
            "-DSQLITE_ENABLE_RTREE",
            "-DSQLITE_ENABLE_DBSTAT_VTAB",
        ))
    if name == "zstd" and not target.is_macos:
        # The static Makefile target is compiled with ZSTD_MULTITHREAD; POSIX
        # threading must also be enabled on the compile line.
        return "-pthread"
    if name == "libedit" and not target.is_macos:
        # musl's stdc-predef.h declares __STDC_ISO_10646__, but clang does
        # not auto-include it; libedit's chartype.h #errors without it.
        # musl's own value is 201206L.
        return "-D__STDC_ISO_10646__=201206L"
    return ""


def make_targets(name: str) -> tuple[str, ...]:
    if name == "bzip2":
        return ("libbz2.a",)
    if name == "zstd":
        # The plain static target is single-threaded even when zstd's
        # Makefile builds a multi-threaded shared library by default.
        return ("libzstd.a-mt",)
    if name == "openssl":
        return ()
    return ()


def special_install(name: str, source: Path, prefix: Path, log: Path) -> bool:
    """Bespoke install for packages without a usable `make install` step.

    `source` is the scratch tree; nesting is resolved per package here.
    """
    if name == "bzip2":
        nested = source / "bzip2-1.0.8"
        (prefix / "lib").mkdir(parents=True, exist_ok=True)
        (prefix / "include").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(nested / "libbz2.a", prefix / "lib" / "libbz2.a")
        shutil.copyfile(nested / "bzlib.h", prefix / "include" / "bzlib.h")
        log.open("a").write("bzip2: manual static install from nested tree\n")
        return True
    if name == "zstd":
        nested = source / "cpython-source-deps-zstd-1.5.7" / "lib"
        (prefix / "lib").mkdir(parents=True, exist_ok=True)
        (prefix / "include").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(nested / "libzstd.a", prefix / "lib" / "libzstd.a")
        for header in ("zstd.h", "zstd_errors.h", "zdict.h"):
            shutil.copyfile(nested / header, prefix / "include" / header)
        log.open("a").write("zstd: manual static install from source-deps tree\n")
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Non-hermetic dependency development builds")
    parser.add_argument("--only", choices=EXTRACT_DIRS)
    args = parser.parse_args()
    work = REPO / "build" / "work"
    prefix = (REPO / "build" / "prefix").resolve()
    logs = REPO / "build" / "logs"
    # A full build owns the prefix and the scratch area; `--only` is the
    # incremental path and keeps both. Reusing a prefix across runs let a
    # stale libncursesw.a from an earlier configuration be linked into the
    # interpreter even after ncurses was dropped from the dependency set —
    # an undeclared input that only showed up by inspecting load commands.
    # Clearing here also makes a rebuild repeatable without a human having to
    # remember that build_recipe refuses to reuse a scratch tree.
    if args.only:
        work.mkdir(parents=True, exist_ok=True)
        prefix.mkdir(parents=True, exist_ok=True)
    else:
        for directory in (work, prefix):
            if directory.exists():
                print(f"CLEAN {directory}", flush=True)
                shutil.rmtree(directory)
            directory.mkdir(parents=True)
    cache = Cache(REPO / ".cache")
    lock = {e.name: e for e in load_lock(REPO / "sources.lock.json")}
    try:
        target = native_target()
        toolchain = toolchain_for(target, REPO / "bootstrap.lock.json")
    except (UnsupportedTargetError, BootstrapError) as error:
        print(f"FAIL deps: {error}")
        return 1

    if target.is_macos:
        # The LTO gate runs before anything large is compiled:
        # a compiler/linker generation mismatch is cheap to detect here and
        # expensive to discover after an hour of OpenSSL.
        try:
            smoke = lto_smoke_test(toolchain, logs / "lto-smoke")
        except BootstrapError as error:
            print(f"FAIL deps: {error}")
            return 1
        (logs / "lto-smoke.json").write_text(
            json.dumps(smoke, indent=2, sort_keys=True) + "\n"
        )
        print(f"LTO   thin ok ({smoke['arch']}, minos {smoke['minos']})", flush=True)

    for name in dependency_order(target):
        if args.only and name != args.only:
            continue
        if name == "pkgconf":
            continue  # host tool (Alpine apk or Homebrew), not shipped
        if name not in lock:
            print(f"SKIP {name}: not in lock")
            continue
        entry = lock[name]
        blob = cache.require(entry)
        extract_dir = EXTRACT_DIRS.get(name)
        if extract_dir is None:
            print(f"SKIP {name}: no extract_dir mapping")
            continue
        dest = work / name
        recipe = Recipe(
            name=name,
            extract_dir=extract_dir,
            source_subdir=SOURCE_SUBDIRS.get(name, ""),
            build_subdir="db-6.0.19/build_unix" if name == "bdb" else "",
            configure_args=configure_args(name, target=target),
            make_targets=make_targets(name),
            cflags=cflags_for(name, target),
            install=install_style(name),
            log_path=logs / name,
        )
        print(f"BUILD {name} {entry.version}", flush=True)
        try:
            build_recipe(recipe, blob, work, prefix, toolchain=toolchain)
            if special_install(name, dest, prefix, logs / f"{name}-special.log"):
                pass
        except (BuildError, InputError) as error:
            print(f"FAIL {name}: {error}")
            return 1
        print(f"OK    {name}", flush=True)
    print("all dependencies built")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
