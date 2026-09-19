"""Order the dependency build, honoring inter-library configure needs.

The two families build genuinely different sets, because macOS supplies
several of these libraries as part of the platform (plan Section 5.2) rather
than bundling them:

  linux-musl  builds all thirteen; the Alpine container has no equivalent
              system library to borrow.
  macos       builds eight. zlib, Expat, and libedit come from the platform,
              and libuuid and Berkeley DB are not inputs at all: `_uuid` and
              `dbm.ndbm` use platform facilities on Darwin, which also keeps
              an AGPL-licensed component out of the macOS payload.
"""

from __future__ import annotations

from .targets import MACOS, Target

# Ordering constraints:
#   pkg-config must exist before any pkg-config consumer configures.
#   zlib/zstd feed openssl's optional compression and sqlite's.
#   ncurses feeds libedit (curses/termcap fallback) and curses modules.
LINUX_DEPENDENCY_ORDER: tuple[str, ...] = (
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

# macOS ordering constraints are weaker: none of these consumes another's
# build artifacts, so the order is chosen for fast failure (cheap libraries
# first) with the slowest — OpenSSL — last.
#
# The set is not the Linux one minus exclusions; it was derived from the
# pinned reference's own Mach-O load commands (plan 5.2 requires confirming
# the split against the artifact rather than trusting the summary table). The
# reference links `/usr/lib/libncurses.5.4.dylib`, `/usr/lib/libpanel.5.4.dylib`,
# `/usr/lib/libz.1.dylib` and `/usr/lib/libedit.3.dylib`, and shows no
# libexpat load command — so ncurses and zlib and libedit are the platform's,
# while Expat is statically linked from source like the rest.
MACOS_DEPENDENCY_ORDER: tuple[str, ...] = (
    "bzip2",
    "xz",
    "zstd",
    "mpdecimal",
    "libffi",
    "expat",
    "sqlite",
    "openssl",
)

ORDERS = {"linux-musl": LINUX_DEPENDENCY_ORDER, MACOS: MACOS_DEPENDENCY_ORDER}

# Retained for the frozen Linux importers and tests; prefer dependency_order().
DEPENDENCY_ORDER = LINUX_DEPENDENCY_ORDER


def dependency_order(target: Target) -> tuple[str, ...]:
    """The dependency build order for one target's family."""
    try:
        return ORDERS[target.family]
    except KeyError:
        raise KeyError(f"no dependency order for family {target.family!r}") from None
