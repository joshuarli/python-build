"""CPython 3.14.6 configuration policy (plan 5.3).

Values derive from the verified 3.14.6 `configure --help` output, not memory:
LTO is explicit ThinLTO, PGO/BOLT/JIT/tail-call stay off, ensurepip is
deferred to a pinned offline pip wheel, and every third-party dependency is
pinned to the private prefix so host packages cannot be detected.

The two families differ in more than flag spelling, and the differences are
consequences of the platform rather than preferences:

  linux-musl  Every dependency is bundled, dbm is Berkeley DB, readline is a
              private libedit, and musl's small default thread stack needs an
              explicit raise.
  macos       zlib, libedit, and ncurses/panel are the platform's own, while
              Expat is linked from source like the rest — a split measured
              from the pinned reference's load commands, not assumed. dbm is
              ndbm and `_uuid` uses platform facilities, so neither libuuid
              nor Berkeley DB is an input. No ELF loader-hardening or
              build-id flags exist, and the musl thread-stack policy does not
              apply.
"""

from __future__ import annotations

from pathlib import Path

from .targets import Target, native_target


def configuration(prefix: Path, target: Target | None = None) -> tuple[list[str], dict[str, str]]:
    prefix = Path(prefix)
    target = target or native_target()
    if target.is_macos:
        return _macos_configuration(prefix, target)
    return _linux_musl_configuration(prefix, target)


def _base_env(prefix: Path) -> dict[str, str]:
    """Dependency-selection variables shared by both families.

    These cover the libraries this project builds itself. Anything absent
    here is deliberately left to the platform: on macOS that is zlib, Expat,
    and libedit, which configure finds in the SDK because no private copy
    shadows them.
    """
    return {
        "BZIP2_CFLAGS": f"-I{prefix}/include",
        "BZIP2_LIBS": f"-L{prefix}/lib {prefix}/lib/libbz2.a",
        "LIBLZMA_CFLAGS": f"-I{prefix}/include",
        "LIBLZMA_LIBS": f"-L{prefix}/lib {prefix}/lib/liblzma.a",
        "LIBZSTD_CFLAGS": f"-I{prefix}/include",
        "LIBZSTD_LIBS": f"-L{prefix}/lib {prefix}/lib/libzstd.a",
        "LIBFFI_CFLAGS": f"-I{prefix}/include",
        "LIBFFI_LIBS": f"-L{prefix}/lib {prefix}/lib/libffi.a",
        "LIBMPDEC_CFLAGS": f"-I{prefix}/include",
        "LIBMPDEC_LIBS": f"-L{prefix}/lib {prefix}/lib/libmpdec.a -lm",
        "LIBSQLITE3_CFLAGS": f"-I{prefix}/include",
        "CPPFLAGS": f"-I{prefix}/include",
        "OPENSSL_INCLUDES": f"-I{prefix}/include",
    }


# Configure arguments that encode the product policy and are identical on
# every platform: LTO without PGO/BOLT/JIT/tail-call, shared libpython, and
# ensurepip deferred to the pinned wheel. The Linux branch spells its own
# list out rather than sharing this tuple so its argument order stays
# byte-identical to the frozen build that produced its evidence.
COMMON_POLICY_ARGS = (
    "--with-lto=thin",
    "--enable-shared",
    "--enable-experimental-jit=no",
    "--with-tail-call-interp=no",
    "--without-static-libpython",
    "--with-ensurepip=no",
    "--without-ensurepip",
)


def _linux_musl_configuration(prefix: Path, target: Target) -> tuple[list[str], dict[str, str]]:
    env = {
        **_base_env(prefix),
        "PKG_CONFIG_LIBDIR": f"{prefix}/lib/pkgconfig:{prefix}/share/pkgconfig",
        "LIBUUID_CFLAGS": f"-I{prefix}/include/uuid",
        "LIBUUID_LIBS": f"-L{prefix}/lib {prefix}/lib/libuuid.a",
        # Linux bundles ncurses/panel; macOS links the platform's 5.4 instead
        # (measured from the reference's load commands), so these must not be
        # set on that family — doing so silently links whatever static library
        # happens to be sitting in the prefix.
        "CURSES_CFLAGS": f"-I{prefix}/include -I{prefix}/include/ncursesw",
        "CURSES_LIBS": f"-L{prefix}/lib {prefix}/lib/libncursesw.a",
        "PANEL_CFLAGS": f"-I{prefix}/include/ncursesw",
        "PANEL_LIBS": f"-L{prefix}/lib {prefix}/lib/libpanelw.a {prefix}/lib {prefix}/lib/libncursesw.a",
        "LIBSQLITE3_LIBS": f"-L{prefix}/lib {prefix}/lib/libsqlite3.a -ldl -lpthread",
        "LIBEDIT_CFLAGS": f"-I{prefix}/include -I{prefix}/include/editline",
        "LIBEDIT_LIBS": f"-L{prefix}/lib {prefix}/lib/libedit.a {prefix}/lib/libncursesw.a",
        "DBM_CFLAGS": f"-I{prefix}/include",
        "DBM_LIBS": f"-L{prefix}/lib {prefix}/lib/libdb.a",
        "ZLIB_CFLAGS": f"-I{prefix}/include",
        "ZLIB_LIBS": f"{prefix}/lib/libz.a",
        # No -rpath here: a $ORIGIN token written through configure's
        # Makefile substitution is expanded twice (once by make, once by
        # the recipe's /bin/sh), which cannot produce a literal single-$
        # token in both the build's own link commands and the installed
        # sysconfigdata LDFLAGS that pip reads directly (no shell involved)
        # at the same time. Relative RPATHs are set as a structured
        # post-install ELF edit instead (build/relocate.py, plan 6).
        "LDFLAGS": f"-L{prefix}/lib -Wl,-z,noexecstack -Wl,--build-id=sha1",
        "CFLAGS": (
            f"-O3 {target.cpu_baseline_cflag} -fno-omit-frame-pointer -fPIC -fstack-protector-strong "
            "-D_FORTIFY_SOURCE=2"
        ),
    }
    args = [
        "--with-lto=thin",
        "--enable-shared",
        "--without-ensurepip",
        "--enable-experimental-jit=no",
        "--with-system-expat",
        "--with-system-libmpdec",
        "--with-openssl=" + str(prefix),
        "--with-openssl-rpath=no",
        "--with-dbmliborder=bdb:ndbm:gdbm",
        # Plan 5.2 forbids silently replacing libedit with readline; the
        # readline module must link against the private libedit build, not
        # probe for a system GNU readline that isn't part of this product.
        "--with-readline=editline",
        "--with-tail-call-interp=no",
        "--without-static-libpython",
        "--with-ensurepip=no",
        # Musl default thread stack (128 KiB) is too small for CPython
        # recursion depth (Alpine carries the same 2 MiB policy).
        "CFLAGS_NODIST=-DTHREAD_STACK_SIZE=0x200000",
    ]
    return args, env


def _macos_configuration(prefix: Path, target: Target) -> tuple[list[str], dict[str, str]]:
    env = {
        **_base_env(prefix),
        # Lock dependency detection to the private prefix. Without this,
        # pkg-config's default search path includes Homebrew's, which carries
        # .pc files for openssl/sqlite/libffi at different versions and would
        # let configure satisfy a probe from the builder's prefix. The Linux
        # branch keeps its original PKG_CONFIG_PATH because its container has
        # no competing prefix.
        "PKG_CONFIG_LIBDIR": f"{prefix}/lib/pkgconfig:{prefix}/share/pkgconfig",
        "PKG_CONFIG_PATH": f"{prefix}/lib/pkgconfig:{prefix}/share/pkgconfig",
        # Platform libraries, matching the reference's load commands: it links
        # /usr/lib/libedit.3.dylib, /usr/lib/libz.1.dylib,
        # /usr/lib/libncurses.5.4.dylib and /usr/lib/libpanel.5.4.dylib. No
        # private copy shadows any of them, so the probe finds the SDK's.
        "LIBEDIT_CFLAGS": "",
        "LIBEDIT_LIBS": "-ledit",
        # Expat is the exception: the reference carries no libexpat load
        # command, so it statically links its own. CPPFLAGS/LDFLAGS put the
        # private prefix first, which makes configure's -lexpat probe resolve
        # to the bundled libexpat.a rather than the SDK's dylib.
        "LIBSQLITE3_LIBS": f"-L{prefix}/lib {prefix}/lib/libsqlite3.a",
        "LDFLAGS": (
            f"-L{prefix}/lib -mmacosx-version-min={target.deployment_target} "
            # install_name_tool must rewrite libpython's id and the
            # interpreter's dependency on it, and adding an LC_RPATH needs
            # room the default header layout does not leave (plan Section 6).
            "-Wl,-headerpad_max_install_names"
        ),
        "CFLAGS": (
            f"-O3 {target.cpu_baseline_cflag} -fno-omit-frame-pointer -fPIC "
            f"-mmacosx-version-min={target.deployment_target}"
        ),
    }
    args = [
        *COMMON_POLICY_ARGS,
        # `--with-system-expat` means "use an external Expat rather than a
        # vendored one"; the search path above decides *which* external one.
        "--with-system-expat",
        "--with-system-libmpdec",
        "--with-openssl=" + str(prefix),
        "--with-openssl-rpath=no",
        # Darwin's _uuid uses platform facilities and dbm uses ndbm; neither
        # libuuid nor Berkeley DB is built or shipped (plan Section 5.2).
        "--with-dbmliborder=ndbm",
        "--with-readline=editline",
    ]
    return args, env
