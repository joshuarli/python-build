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

import ast
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Iterable

ELF_MAGIC = b"\x7fELF"

_RELOCATABLE_SYSCONFIG_MARKER = "# python-build relocatable sysconfig values"
_BUILD_ONLY_FLAGS = re.compile(
    r"(?<!\S)(?:-fprofile-instr-use|-resource-dir)(?:=|\s+)\S+"
    r"|(?<!\S)-isysroot(?:=|\s+)\S+"
)
_BUILD_ONLY_PROFILE_KEYS = frozenset({
    "LLVM_PROF_FILE", "LLVM_PROF_MERGER", "PGO_PROF_GEN_FLAG",
    "PGO_PROF_USE_FLAG", "PROFILE_TASK",
})
_COMMAND_VARIABLES = frozenset({
    "AR", "CC", "CXX", "INSTALL", "LD", "LINKCC", "LDCXXSHARED",
    "LDSHARED", "MAKE", "NM", "RANLIB", "STRIP",
})


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


def _clean_build_value(
    value: str,
    key: str,
    builder_paths: tuple[Path, ...],
    command_paths: tuple[Path, ...],
) -> str:
    """Remove builder-only inputs while retaining usable consumer commands."""
    if key in _BUILD_ONLY_PROFILE_KEYS:
        return ""
    cleaned = value
    for command_path in command_paths:
        cleaned = cleaned.replace(str(command_path), command_path.name)
    cleaned = _BUILD_ONLY_FLAGS.sub("", cleaned)
    for builder_path in builder_paths:
        cleaned = strip_private_prefix(cleaned, builder_path)

    if key in _COMMAND_VARIABLES:
        try:
            words = shlex.split(cleaned)
        except ValueError as error:
            raise RelocationError(f"cannot parse sysconfig command {key}: {error}") from error
        if words and Path(words[0]).is_absolute():
            words[0] = Path(words[0]).name
            cleaned = shlex.join(words)
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip()


def _sysconfigdata_assignment(source: str, path: Path) -> tuple[ast.Module, ast.Assign]:
    try:
        module = ast.parse(source, filename=str(path))
    except SyntaxError as error:
        raise RelocationError(f"cannot parse generated sysconfigdata {path}: {error}") from error
    assignments = [
        node
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "build_time_vars"
                for target in node.targets)
    ]
    if (
        len(assignments) != 1
        or not isinstance(assignments[0].value, ast.Dict)
        or len(module.body) != 1
    ):
        raise RelocationError(
            f"unexpected generated sysconfigdata layout in {path}; expected one literal build_time_vars dictionary"
        )
    return module, assignments[0]


def _relocate_sysconfigdata(
    path: Path,
    *,
    builder_paths: tuple[Path, ...],
    command_paths: tuple[Path, ...],
    configure_prefix: str,
) -> bool:
    source = path.read_text()
    if _RELOCATABLE_SYSCONFIG_MARKER in source:
        return False

    _, assignment = _sysconfigdata_assignment(source, path)
    values = assignment.value
    assert isinstance(values, ast.Dict)
    lines = source.splitlines()
    header = "\n".join(lines[: assignment.lineno - 1]).rstrip()
    output = (header + "\n" if header else "") + "build_time_vars = {\n"
    for key_node, value_node in zip(values.keys, values.values):
        if key_node is None:
            raise RelocationError(f"unexpected dictionary unpack in {path}")
        try:
            key = ast.literal_eval(key_node)
            value = ast.literal_eval(value_node)
        except (ValueError, TypeError, SyntaxError) as error:
            raise RelocationError(
                f"unexpected non-literal sysconfig value in {path}: {error}"
            ) from error
        if not isinstance(key, str):
            raise RelocationError(f"non-string sysconfig key in {path}: {key!r}")
        if isinstance(value, str):
            rendered_value = repr(
                _clean_build_value(value, key, builder_paths, command_paths)
            )
        else:
            rendered_value = ast.unparse(value_node)
        output += f"    {key!r}: {rendered_value},\n"
    output += "}\n\n"
    output += (
        f"{_RELOCATABLE_SYSCONFIG_MARKER}\n"
        "import os as _python_build_os\n"
        "import re as _python_build_re\n"
        "_python_build_root = _python_build_os.path.dirname(\n"
        "    _python_build_os.path.dirname(\n"
        "        _python_build_os.path.dirname(\n"
        "            _python_build_os.path.realpath(__file__)\n"
        "        )\n"
        "    )\n"
        ")\n"
        f"_python_build_prefix = {configure_prefix!r}\n"
        "_python_build_prefix_pattern = _python_build_re.compile(\n"
        "    _python_build_re.escape(_python_build_prefix) + r'(?=$|[^A-Za-z0-9_.-])'\n"
        ")\n"
        "for _python_build_key, _python_build_value in tuple(build_time_vars.items()):\n"
        "    if isinstance(_python_build_value, str):\n"
        "        build_time_vars[_python_build_key] = _python_build_prefix_pattern.sub(\n"
        "            lambda _: _python_build_root, _python_build_value\n"
        "        )\n"
        "del _python_build_key, _python_build_value\n"
        "del _python_build_prefix_pattern, _python_build_prefix, _python_build_root\n"
        "del _python_build_os, _python_build_re\n"
    )
    if output == source:
        return False
    path.write_text(output)
    return True


def _rewrite(
    path: Path,
    builder_paths: tuple[Path, ...],
    command_paths: tuple[Path, ...],
    configure_prefix: str,
) -> bool:
    original = path.read_text()
    cleaned = original
    prefix_pattern = re.compile(
        re.escape(configure_prefix) + r"(?=$|[^A-Za-z0-9_.-])"
    )
    if prefix_pattern.search(cleaned):
        cleaned = prefix_pattern.sub("$(_PYTHON_BUILD_PREFIX)", cleaned)
        if "_PYTHON_BUILD_PREFIX := " not in cleaned:
            cleaned = (
                "_PYTHON_BUILD_PREFIX := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../../..)\n"
                + cleaned
            )
    for key in _BUILD_ONLY_PROFILE_KEYS:
        cleaned = re.sub(
            rf"(?m)^([ \t]*{re.escape(key)}[ \t]*=).*$",
            rf"\1",
            cleaned,
        )
    for command_path in command_paths:
        cleaned = cleaned.replace(str(command_path), command_path.name)
    cleaned = _BUILD_ONLY_FLAGS.sub("", cleaned)
    for builder_path in builder_paths:
        cleaned = strip_private_prefix(cleaned, builder_path)
    if cleaned == original:
        return False
    path.write_text(cleaned)
    return True


def _fix_python_config_scripts(install: Path) -> list[Path]:
    """Shell-quote compiler flags so config scripts survive prefix spaces."""
    scripts = [install / "bin" / "python3.14-config"]
    scripts.extend(sorted((install / "lib").rglob("python-config.py")))
    changed: list[Path] = []
    for script in scripts:
        if not script.is_file():
            continue
        source = script.read_text()
        try:
            module = ast.parse(source, filename=str(script))
        except SyntaxError as error:
            if script.name == "python3.14-config" and source.startswith("#!/bin/sh\n"):
                rewritten = _fix_shell_python_config_script(source, script)
                if rewritten != source:
                    script.write_text(rewritten)
                    changed.append(script)
                continue
            raise RelocationError(f"cannot parse python-config script {script}: {error}") from error

        printers: dict[str, list[ast.Call]] = {"flags": [], "libs": []}
        has_shlex_import = any(
            isinstance(node, ast.Import)
            and any(alias.name == "shlex" for alias in node.names)
            for node in module.body
        )
        for node in ast.walk(module):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
                and len(node.args) == 1
            ):
                continue
            output = node.args[0]
            if not isinstance(output, ast.Call) or not isinstance(output.func, ast.Attribute):
                continue
            if output.func.attr != "join" or len(output.args) != 1:
                continue
            joined = output.args[0]
            if not isinstance(joined, ast.Name) or joined.id not in printers:
                continue
            is_space_join = (
                isinstance(output.func.value, ast.Constant)
                and output.func.value.value == " "
            )
            is_shlex_join = (
                isinstance(output.func.value, ast.Name)
                and output.func.value.id == "shlex"
            )
            if is_space_join or is_shlex_join:
                printers[joined.id].append(node)

        counts = {name: len(nodes) for name, nodes in printers.items()}
        if counts != {"flags": 1, "libs": 1}:
            raise RelocationError(
                f"unexpected python-config flag output in {script}; found {counts}, expected one cflags and library output"
            )

        rewritten_bytes = source.encode("utf-8")
        line_offsets = [0]
        for line in source.splitlines(keepends=True):
            line_offsets.append(line_offsets[-1] + len(line.encode("utf-8")))
        replacements = [
            (
                line_offsets[node.lineno - 1] + node.col_offset,
                line_offsets[node.end_lineno - 1] + node.end_col_offset,
                f"print(shlex.join({name}))".encode("ascii"),
            )
            for name, nodes in printers.items()
            for node in nodes
            if not (
                isinstance(node.args[0], ast.Call)
                and isinstance(node.args[0].func, ast.Attribute)
                and isinstance(node.args[0].func.value, ast.Name)
                and node.args[0].func.value.id == "shlex"
            )
        ]
        for start, end, replacement in sorted(replacements, reverse=True):
            rewritten_bytes = rewritten_bytes[:start] + replacement + rewritten_bytes[end:]
        rewritten = rewritten_bytes.decode("utf-8")
        if not has_shlex_import:
            getopt_import = next(
                (
                    node for node in module.body
                    if isinstance(node, ast.Import)
                    and any(alias.name == "getopt" for alias in node.names)
                ),
                None,
            )
            if getopt_import is None or getopt_import.end_lineno is None:
                raise RelocationError(f"unexpected python-config imports in {script}")
            insertion = line_offsets[getopt_import.end_lineno]
            rewritten_bytes = rewritten.encode("utf-8")
            rewritten_bytes = (
                rewritten_bytes[:insertion]
                + b"import shlex\n"
                + rewritten_bytes[insertion:]
            )
            rewritten = rewritten_bytes.decode("utf-8")
        if rewritten == source:
            continue
        script.write_text(rewritten)
        changed.append(script)
    return changed


def _fix_shell_python_config_script(source: str, path: Path) -> str:
    """Quote tokens printed by CPython's Linux shell python-config wrapper."""
    rewrites = {
        'echo "$INCDIR $PLATINCDIR"': 'quote_args "$INCDIR" "$PLATINCDIR"',
        'echo "$INCDIR $PLATINCDIR $BASECFLAGS $CFLAGS $OPT"': (
            'quote_args "$INCDIR" "$PLATINCDIR" $BASECFLAGS $CFLAGS $OPT'
        ),
        'echo "$LIBS"': 'quote_args $LIBS',
        'echo "$LIBPLUSED -L$libdir $LIBS"': (
            'quote_args $LIBPLUSED "-L$libdir" $LIBS'
        ),
    }
    output = source
    for original, replacement in rewrites.items():
        if output.count(original) != 1:
            raise RelocationError(
                f"unexpected python-config shell output in {path}: "
                f"expected one {original!r}, found {output.count(original)}"
            )
        output = output.replace(original, replacement, 1)
    helper = (
        '\nquote_args() {\n'
        '    "$(dirname "$0")/python3.14" -c '
        "'import shlex, sys; print(shlex.join(sys.argv[1:]))' \"$@\"\n"
        '}\n'
    )
    return output.replace("#!/bin/sh\n", "#!/bin/sh\n" + helper, 1)


def clean_sysconfig(
    staged_install: Path,
    private_prefix: Path,
    *,
    configure_prefix: str = "/install",
    builder_paths: Iterable[Path] = (),
    command_paths: Iterable[Path] = (),
) -> list[Path]:
    """Make installed sysconfig metadata follow the moved tree.

    CPython records the configure-time prefix and build-tool paths in its
    generated sysconfigdata and Makefile. Sysconfigdata resolves that prefix
    from its own installed location at import time; all other builder paths
    are removed or reduced to executable names so consumers can build
    extensions without the original checkout, dependency prefix, SDK, or
    compiler cache. `python3.14-config` shell-quotes its flag lists so a
    relocated install under a path containing spaces remains usable.
    """
    roots = tuple(dict.fromkeys(
        Path(path).resolve() for path in (private_prefix, *builder_paths)
        if str(path)
    ))
    commands = tuple(dict.fromkeys(
        Path(path) for path in command_paths
        if str(path) and Path(path).is_absolute()
    ))
    changed: list[Path] = []
    lib = staged_install / "lib"
    for sysconfigdata in lib.rglob("_sysconfigdata_*.py"):
        if _relocate_sysconfigdata(
            sysconfigdata,
            builder_paths=roots,
            command_paths=commands,
            configure_prefix=configure_prefix,
        ):
            changed.append(sysconfigdata)
        remaining = sysconfigdata.read_text()
        leaked = [str(path) for path in (*roots, *commands) if str(path) in remaining]
        if leaked:
            raise RelocationError(
                f"sysconfigdata still contains builder paths in {sysconfigdata}: "
                + ", ".join(leaked)
            )
        # A stale bytecode cache would shadow the rewritten source on import.
        cache = sysconfigdata.parent / "__pycache__"
        if cache.is_dir():
            for compiled in cache.glob(f"{sysconfigdata.stem}.*.pyc"):
                compiled.unlink()

    if not changed and not list(lib.rglob("_sysconfigdata_*.py")):
        raise RelocationError(f"no generated sysconfigdata found under {lib}")

    for makefile in lib.rglob("Makefile"):
        if _rewrite(makefile, roots, commands, configure_prefix):
            changed.append(makefile)
        remaining = makefile.read_text()
        leaked = [str(path) for path in (*roots, *commands) if str(path) in remaining]
        if re.search(
            re.escape(configure_prefix) + r"(?=$|[^A-Za-z0-9_.-])", remaining
        ):
            leaked.append(configure_prefix)
        if leaked:
            raise RelocationError(
                f"installed Makefile still contains builder paths in {makefile}: "
                + ", ".join(leaked)
            )
    changed.extend(_fix_python_config_scripts(Path(staged_install)))
    return changed


# A shebang cannot be relative, so a script whose first line names the
# configure-time prefix (`#!/install/bin/python3.14`) is dead the moment the
# tree is staged, and stays dead after relocation. CPython writes exactly
# that for pydoc3, idle3 and python3.14-config (`@EXENAME@` in
# Makefile.pre.in), and ensurepip writes it again for the pip launchers.
#
# The replacement is the standard sh/Python polyglot: sh reads the second
# line as `exec <interpreter> "$0" "$@"`, while Python sees a triple-quoted
# string literal and skips it. `readlink -f` is available on macOS 12.3+ and
# on any glibc/musl userspace this project targets, and resolves the case
# where the launcher itself was reached through a symlink — which is exactly
# how `pip3` is usually invoked.
POLYGLOT_PREFIX = (
    "#!/bin/sh\n"
    "'''exec' \"$(dirname \"$(readlink -f -- \"$0\")\")/{interpreter}\" \"$0\" \"$@\"\n"
    "' '''\n"
)


def _is_interpreter_shebang(line: str, interpreter: str) -> bool:
    if not line.startswith("#!"):
        return False
    target = line[2:].strip()
    return Path(target).name.startswith(interpreter.rsplit(".", 1)[0])


def fix_script_shebangs(install: Path, interpreter: str = "python3.14") -> list[Path]:
    """Make installed launcher scripts relocatable; return the ones rewritten.

    Only files that actually name an interpreter are touched, and an already
    rewritten script is left alone, so this is idempotent.
    """
    changed: list[Path] = []
    binary = Path(install) / "bin"
    if not binary.is_dir():
        return changed
    for script in sorted(binary.iterdir()):
        if script.is_symlink() or not script.is_file():
            continue
        try:
            original = script.read_text()
        except (OSError, UnicodeDecodeError):
            continue  # binaries and non-UTF-8 payloads are not scripts
        first, _, rest = original.partition("\n")
        if not _is_interpreter_shebang(first, interpreter):
            continue
        if rest.startswith("'''exec'"):
            continue  # already rewritten by an earlier run
        script.write_text(POLYGLOT_PREFIX.format(interpreter=interpreter) + rest)
        script.chmod(script.stat().st_mode | 0o111)
        changed.append(script)
    return changed


def relocate(
    staged_install: Path,
    private_prefix: Path,
    *,
    patchelf: str = "patchelf",
    configure_prefix: str = "/install",
    builder_paths: Iterable[Path] = (),
    command_paths: Iterable[Path] = (),
) -> list[Path]:
    """Apply both fixups to a staged `make install` tree; return changed ELFs."""
    lib_dir = staged_install / "lib"
    touched = []
    for elf in find_elfs(staged_install):
        set_relative_rpath(elf, lib_dir, patchelf=patchelf)
        touched.append(elf)
    clean_sysconfig(
        staged_install,
        private_prefix,
        configure_prefix=configure_prefix,
        builder_paths=builder_paths,
        command_paths=command_paths,
    )
    fix_script_shebangs(staged_install)
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
    builder_paths: Iterable[Path] = (),
    command_paths: Iterable[Path] = (),
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

    clean_sysconfig(
        install,
        private_prefix,
        configure_prefix=configure_prefix,
        builder_paths=builder_paths,
        command_paths=command_paths,
    )
    fix_script_shebangs(install)
    return touched
