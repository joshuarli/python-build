"""Order the dependency build, honoring inter-library configure needs."""

from __future__ import annotations

# Ordering constraints:
#   pkg-config must exist before any pkg-config consumer configures.
#   zlib/zstd feed openssl's optional compression and sqlite's.
#   ncurses feeds libedit (curses/termcap fallback) and curses modules.
DEPENDENCY_ORDER: tuple[str, ...] = (
    "pkgconf",  # host tool, not shipped; see host_tool()
    "zlib",
    "bzip2",
    "xz",
    "zstd",
    "expat",
    "mpdecimal",
    "libffi",
    "ncurses",
    "libedit",
    "libuuid",
    "bdb",
    "sqlite",
    "openssl",
    # Tcl/Tk and their X11 closure are deliberately outside the product scope.
)
