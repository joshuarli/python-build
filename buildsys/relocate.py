"""Post-install relocation fixups for the staged CPython tree (plan 6).

CPython's own install produces two things that cannot survive into a
relocatable artifact: ELF binaries with no runtime search path to their
sibling libpython, and a sysconfigdata module whose LDFLAGS/CFLAGS/LDSHARED
still name the private builder-only dependency prefix (plan Section 6:
"Consumer compiler settings must not refer to the private dependency
prefix ... that only existed inside the builder"). Both are fixed here as
structured edits over the installed tree.

$ORIGIN rpaths are set with patchelf rather than through configure's
LDFLAGS: a `$ORIGIN` token written into a Makefile variable is expanded
once by make and once by the recipe's /bin/sh, so it cannot reach both
CPython's own link commands *and* the installed sysconfigdata LDFLAGS
(read directly by pip with no shell involved) as a literal single-`$`
token at the same time. patchelf takes the rpath as a plain argv element,
so a literal '$ORIGIN' reaches the ELF dynamic section unescaped.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ELF_MAGIC = b"\x7fELF"

# Consumer-facing sysconfigdata keys read by distutils/setuptools/pip when
# building third-party C extensions (plan Section 6). Per-module keys like
# MODULE__SSL_LDFLAGS are build provenance for CPython's own stdlib modules,
# not part of that consumer contract, and are left alone.
CONSUMER_FLAG_KEYS = (
    "BASECFLAGS", "BLDSHARED", "CFLAGS", "CFLAGS_NODIST", "CONFIGURE_CFLAGS",
    "CONFIGURE_CPPFLAGS", "CONFIGURE_LDFLAGS", "CPPFLAGS", "LDCXXSHARED",
    "LDFLAGS", "LDFLAGS_NODIST", "LDSHARED", "OPT", "PY_CFLAGS",
    "PY_CFLAGS_NODIST", "PY_CORE_CFLAGS", "PY_CORE_LDFLAGS", "PY_CPPFLAGS",
    "PY_LDFLAGS", "PY_LDFLAGS_NODIST", "PY_LDFLAGS_NOLTO",
)


class RelocationError(Exception):
    """A staged file could not be relocated for a portable install."""


def is_elf(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(4) == ELF_MAGIC
    except OSError:
        return False


def find_elfs(root: Path) -> list[Path]:
    """Real (non-symlink) ELF files under an installed tree."""
    return sorted(
        path for path in root.rglob("*")
        if path.is_file() and not path.is_symlink() and is_elf(path)
    )


def origin_token(elf: Path, lib_dir: Path) -> str:
    """The $ORIGIN-relative rpath token pointing elf at lib_dir."""
    relative = Path(os.path.relpath(lib_dir, elf.parent))
    return "$ORIGIN" if str(relative) == "." else f"$ORIGIN/{relative}"

def set_relative_rpath(elf: Path, lib_dir: Path, *, patchelf: str = "patchelf") -> None:
    token = origin_token(elf, lib_dir)
    result = subprocess.run(
        [patchelf, "--set-rpath", token, str(elf)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RelocationError(f"patchelf failed on {elf}: {result.stderr}")


def strip_private_prefix(text: str, private_prefix: Path) -> str:
    """Delete every -I/-L/bare token naming the builder-only prefix."""
    needle = re.escape(str(private_prefix).rstrip("/"))
    token = re.compile(rf"(?:-[IL])?{needle}(?:/\S*)?")
    cleaned = token.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", cleaned)


def _rewrite(path: Path, private_prefix: Path) -> bool:
    original = path.read_text()
    cleaned = strip_private_prefix(original, private_prefix)
    if cleaned == original:
        return False
    path.write_text(cleaned)
    return True


def clean_sysconfig(staged_install: Path, private_prefix: Path) -> list[Path]:
    """Strip the private prefix from consumer-facing build configuration.

    Only sysconfigdata's CONSUMER_FLAG_KEYS lines and the installed
    Makefile are edited; per-module MODULE_*_{CFLAGS,LDFLAGS} provenance
    strings are informational and are not part of the pip/distutils
    extension-build contract this project promises (plan 8.1).
    """
    changed: list[Path] = []
    lib = staged_install / "lib"
    for sysconfigdata in lib.rglob("_sysconfigdata_*.py"):
        text = sysconfigdata.read_text()
        rewritten = text
        for key in CONSUMER_FLAG_KEYS:
            pattern = re.compile(rf"('{re.escape(key)}':\s*')([^']*)(')")

            def _clean(match: re.Match[str]) -> str:
                return match.group(1) + strip_private_prefix(match.group(2), private_prefix) + match.group(3)

            rewritten = pattern.sub(_clean, rewritten)
        if rewritten != text:
            sysconfigdata.write_text(rewritten)
            changed.append(sysconfigdata)
        # A stale bytecode cache would shadow the rewritten source on import.
        cache = sysconfigdata.parent / "__pycache__"
        if cache.is_dir():
            for compiled in cache.glob(f"{sysconfigdata.stem}.*.pyc"):
                compiled.unlink()

    for makefile in lib.rglob("Makefile"):
        if _rewrite(makefile, private_prefix):
            changed.append(makefile)
    return changed


def relocate(staged_install: Path, private_prefix: Path, *, patchelf: str = "patchelf") -> list[Path]:
    """Apply both fixups to a staged `make install` tree; return changed ELFs."""
    lib_dir = staged_install / "lib"
    touched = []
    for elf in find_elfs(staged_install):
        set_relative_rpath(elf, lib_dir, patchelf=patchelf)
        touched.append(elf)
    clean_sysconfig(staged_install, private_prefix)
    return touched


# --------------------------------------------------------------------------
# macOS relocation (plan Section 6).
#
# The problem is the same — the interpreter must find its sibling libpython
# after the tree moves — but Mach-O records it differently. There is no
# search-path-independent soname: each consumer stores the *install name* it
# was linked against, so the fix is to give libpython a relocatable id and
# rewrite every reference to match, then give each consumer an LC_RPATH that
# resolves it. `configure_prefix` is whatever `--prefix` CPython was built
# with; nothing may be left referring to it after this runs.
#
# Every edit here invalidates a code signature, and an unsigned Mach-O does
# not launch on Apple Silicon, so the primitives in `buildsys.macho` re-sign
# as part of each edit rather than leaving it to the caller.
# --------------------------------------------------------------------------


def macho_relocate(
    staged_install: Path,
    private_prefix: Path,
    *,
    configure_prefix: str = "/install",
) -> list[Path]:
    """Make a staged `make install` tree relocatable; return the images edited.

    `private_prefix` is the builder-only dependency prefix, which must not
    survive in consumer-facing configuration (same rule as the ELF path).
    `configure_prefix` is CPython's own `--prefix`, baked into every load
    command that names libpython.
    """
    from . import macho

    install = Path(staged_install)
    lib_dir = install / "lib"
    libraries = sorted(lib_dir.glob("libpython3*.dylib"))
    if not libraries:
        raise RelocationError(f"no libpython dylib found under {lib_dir}")
    touched: list[Path] = []
    for library in libraries:
        portable = f"@rpath/{library.name}"
        stale = f"{configure_prefix.rstrip('/')}/lib/{library.name}"
        macho.set_install_name(library, portable)
        touched.append(library)
        for image in macho.find_machos(install):
            if image == library:
                continue
            changed = False
            for dependency in macho.dependencies(image):
                if dependency == stale or Path(dependency).name == library.name:
                    macho.change_dependency(image, dependency, portable, resign=False)
                    changed = True
            if changed:
                touched.append(image)

    # Any image that now loads something via @rpath needs a search path that
    # resolves from its own location, which survives moving the whole tree.
    for image in macho.find_machos(install):
        if not any(d.startswith("@rpath/") for d in macho.dependencies(image)):
            continue
        relative = os.path.relpath(lib_dir, image.parent)
        macho.add_rpath(image, f"@loader_path/{relative}")
        if image not in touched:
            touched.append(image)

    clean_sysconfig(install, private_prefix)
    return touched
