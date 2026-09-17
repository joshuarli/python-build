"""Order the dependency build, honoring inter-library configure needs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .recipes import BuildError, Recipe, Toolchain, build_recipe, run

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


@dataclass
class Plan:
    recipes: dict[str, Recipe]

    def names(self) -> tuple[str, ...]:
        return tuple(self.recipes)


def recipe_for(name: str, version: str, extract_dir: str) -> Recipe:
    common = Recipe(
        name=name,
        extract_dir=extract_dir,
        source_subdir="",
        log_path=Path("build/logs"),
    )
    if name == "zlib":
        # zlib's configure is its own script; it does not accept autoconf args.
        return Recipe(
            **{
                **common.__dict__,
                "configure_args": ("--static",),
            }
        )
    if name == "zstd":
        # zstd: the library Makefile lives in lib/ of the nested source tree.
        return Recipe(
            **{
                **common.__dict__,
                "source_subdir": "cpython-source-deps-zstd-1.5.7/lib",
                "make_targets": ("libzstd.a",),
            }
        )
    if name == "openssl":
        return Recipe(
            **{
                **common.__dict__,
                "configure_args": (
                    "linux-x86_64",
                    "--libdir=lib",
                    "no-shared",
                    "no-docs",
                ),
                "make_targets": ("build_sw", "install_sw"),
            }
        )
    if name == "bzip2":
        return Recipe(
            **{
                **common.__dict__,
                "make_targets": ("libbz2.a",),
            }
        )
    return common
