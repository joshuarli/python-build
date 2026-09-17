"""CPython 3.14.6 configuration policy (plan 5.3).

Values derive from the verified 3.14.6 `configure --help` output, not memory:
LTO is explicit ThinLTO, PGO/BOLT/JIT/tail-call stay off, ensurepip is
deferred to a pinned offline pip wheel, and every third-party dependency is
pinned to the private prefix so host packages cannot be detected.
"""

from __future__ import annotations

from pathlib import Path


def configuration(prefix: Path) -> tuple[list[str], dict[str, str]]:
    prefix = Path(prefix)
    static = {
        "openssl": ["-lssl", "-lcrypto"],
        "sqlite3": ["-lsqlite3", "-ldl", "-lpthread"],
        "zlib": ["-lz"],
        "bzip2": ["-lbz2"],
        "liblzma": ["-llzma", "-lpthread"],
        "zstd": ["-lzstd", "-lpthread"],
        "ffi": ["-lffi"],
        "mpdec": ["-lmpdec", "-lm"],
        "uuid": ["-luuid"],
        "edit": ["-ledit", "-lncursesw"],
        "curses": ["-lncursesw"],
        "db": ["-ldb"],
        "expat": ["-lexpat"],
    }
    env = {
        "PKG_CONFIG_LIBDIR": f"{prefix}/lib/pkgconfig:{prefix}/share/pkgconfig",
        "py_cv_module__tkinter": "disabled",
        "BZIP2_CFLAGS": f"-I{prefix}/include",
        "BZIP2_LIBS": f"-L{prefix}/lib {prefix}/lib/libbz2.a",
        "LIBLZMA_CFLAGS": f"-I{prefix}/include",
        "LIBLZMA_LIBS": f"-L{prefix}/lib {prefix}/lib/liblzma.a",
        "LIBZSTD_CFLAGS": f"-I{prefix}/include",
        "LIBZSTD_LIBS": f"-L{prefix}/lib {prefix}/lib/libzstd.a",
        "LIBUUID_CFLAGS": f"-I{prefix}/include/uuid",
        "LIBUUID_LIBS": f"-L{prefix}/lib {prefix}/lib/libuuid.a",
        "LIBFFI_CFLAGS": f"-I{prefix}/include",
        "LIBFFI_LIBS": f"-L{prefix}/lib {prefix}/lib/libffi.a",
        "LIBMPDEC_CFLAGS": f"-I{prefix}/include",
        "LIBMPDEC_LIBS": f"-L{prefix}/lib {prefix}/lib/libmpdec.a -lm",
        "LIBSQLITE3_CFLAGS": f"-I{prefix}/include",
        "LIBSQLITE3_LIBS": f"-L{prefix}/lib {prefix}/lib/libsqlite3.a -ldl -lpthread",
        "CURSES_CFLAGS": f"-I{prefix}/include -I{prefix}/include/ncursesw",
        "CURSES_LIBS": f"-L{prefix}/lib {prefix}/lib/libncursesw.a",
        "PANEL_CFLAGS": f"-I{prefix}/include/ncursesw",
        "PANEL_LIBS": f"-L{prefix}/lib {prefix}/lib/libpanelw.a {prefix}/lib/libncursesw.a",
        "LIBEDIT_CFLAGS": f"-I{prefix}/include -I{prefix}/include/editline",
        "LIBEDIT_LIBS": f"-L{prefix}/lib {prefix}/lib/libedit.a {prefix}/lib/libncursesw.a",
        "DBM_CFLAGS": f"-I{prefix}/include",
        "DBM_LIBS": f"-L{prefix}/lib {prefix}/lib/libdb.a",
        "CPPFLAGS": f"-I{prefix}/include",
        "ZLIB_CFLAGS": f"-I{prefix}/include",
        "ZLIB_LIBS": f"{prefix}/lib/libz.a",
        "OPENSSL_INCLUDES": f"-I{prefix}/include",
        "LDFLAGS": (
            # $$ survives make's variable expansion so the linker sees
            # $ORIGIN (module rpaths must be relative to the installed tree).
            f"-L{prefix}/lib -Wl,-rpath,$$ORIGIN/../lib "
            "-Wl,-z,noexecstack -Wl,--build-id=sha1"
        ),
        "CFLAGS": (
            "-O3 -march=x86-64 -fno-omit-frame-pointer -fPIC -fstack-protector-strong "
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
        "--with-tail-call-interp=no",
        "--without-static-libpython",
        "--with-ensurepip=no",
        # Musl default thread stack (128 KiB) is too small for CPython
        # recursion depth (Alpine carries the same 2 MiB policy).
        "CFLAGS_NODIST=-DTHREAD_STACK_SIZE=0x200000",
    ]
    return args, env
