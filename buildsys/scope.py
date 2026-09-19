"""Product scope exclusions, enforced on the installed tree.

Two exclusions are structural rather than a matter of what happens to get
built, and they need opposite handling:

  GUI (Tcl/Tk, X11)   Tcl/Tk is never acquired and never built, so the
                      `_tkinter` extension is simply absent. The pure-Python
                      `tkinter` package, however, *is* always installed, so it
                      has to be removed as well — an installed-but-unimportable
                      package is worse than an absent one, because a
                      find_spec-style probe reports it as available.
  Packaging           `pip`, `ensurepip` (with its bundled wheel) and `venv`
                      are ordinary parts of the CPython standard library and
                      are installed unconditionally, so they have to be
                      removed deliberately after `make install`.

Both are enforced here rather than by a configure flag because CPython has no
flag for either — and a silent re-addition after a CPython point release is
exactly the kind of drift this module exists to make loud.
"""

from __future__ import annotations

import shutil
from pathlib import Path

# Directory names under lib/pythonX.Y/ that are installed unconditionally and
# must not ship. `ensurepip/_bundled/` carries a full pip wheel, so removing
# only the top-level launcher would leave the installer's bytes in the payload.
EXCLUDED_STDLIB_DIRS = ("ensurepip", "venv", "tkinter", "idlelib")

# GUI-only single modules that cannot function without Tk. `turtle` draws
# through tkinter, and `idlelib` is the IDE built on it; shipping either
# leaves a name that imports-then-fails or a launcher that cannot run.
EXCLUDED_STDLIB_FILES = ("turtle.py",)

# Console scripts under bin/ that exist to drive a package installer.
EXCLUDED_SCRIPT_PREFIXES = ("pip", "idle")


class ScopeError(Exception):
    """A scope exclusion could not be enforced."""


def stdlib_directories(install: Path) -> list[Path]:
    """The lib/pythonX.Y directories of an installed tree."""
    return sorted(p for p in Path(install).glob("lib/python3.*") if p.is_dir())


def enforce_exclusions(install: Path) -> dict:
    """Remove the excluded components from an installed tree.

    Returns a report of what was removed. Idempotent: a second call finds
    nothing and reports nothing, which is what makes it safe to run on a
    re-packaged tree.
    """
    install = Path(install)
    libraries = stdlib_directories(install)
    if not libraries:
        raise ScopeError(f"no lib/python3.* directory under {install}")
    removed: list[str] = []
    for library in libraries:
        for name in EXCLUDED_STDLIB_DIRS:
            target = library / name
            if target.is_dir():
                shutil.rmtree(target)
                removed.append(str(target.relative_to(install)))
        for name in EXCLUDED_STDLIB_FILES:
            target = library / name
            if target.is_file():
                target.unlink()
                removed.append(str(target.relative_to(install)))
    binary = install / "bin"
    if binary.is_dir():
        for script in sorted(binary.iterdir()):
            if script.name.startswith(EXCLUDED_SCRIPT_PREFIXES):
                script.unlink()
                removed.append(str(script.relative_to(install)))
    return {"removed": removed, "install": str(install)}


def verify_exclusions(install: Path) -> list[str]:
    """Every excluded component still present, as human-readable findings."""
    install = Path(install)
    found: list[str] = []
    for library in stdlib_directories(install):
        for name in (*EXCLUDED_STDLIB_DIRS, *EXCLUDED_STDLIB_FILES):
            if (library / name).exists():
                found.append(str((library / name).relative_to(install)))
    binary = install / "bin"
    if binary.is_dir():
        for script in sorted(binary.iterdir()):
            if script.name.startswith(EXCLUDED_SCRIPT_PREFIXES):
                found.append(str(script.relative_to(install)))
    return found


def excluded_module_names() -> list[str]:
    """Importable names the shipped tree must not expose."""
    names = [name for name in EXCLUDED_STDLIB_DIRS]
    names += [Path(name).stem for name in EXCLUDED_STDLIB_FILES]
    # `_tkinter` is the extension; `tkinter` is the package it backs.
    names.append("_tkinter")
    return sorted(set(names))


def probe_in_process(python: Path, modules: list[str] | None = None) -> dict:
    """Ask the built interpreter whether the excluded modules are importable.

    Filesystem absence is necessary but not sufficient — a stray .pyc, a
    zipimport path, or a stale sys.path entry could still make an excluded
    module importable. This checks the actual runtime behaviour, which is what
    the exclusion is about.
    """
    import json
    import subprocess

    names = modules if modules is not None else excluded_module_names()
    code = (
        "import importlib.util as u, json\n"
        f"mods = {names!r}\n"
        "print(json.dumps({m: u.find_spec(m) is not None for m in mods}))\n"
    )
    result = subprocess.run(
        [str(python), "-c", code], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise ScopeError(
            f"could not probe {python}: {result.stderr.strip() or result.stdout.strip()}"
        )
    return json.loads(result.stdout.strip().splitlines()[-1])
