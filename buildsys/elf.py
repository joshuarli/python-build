"""ELF security properties that can be checked in final package bytes."""

from __future__ import annotations

import re
import shlex
from pathlib import Path, PurePosixPath

_STACK_TYPES = frozenset({"GNU_STACK", "PT_GNU_STACK"})
_PROGRAM_FLAGS = re.compile(r"[RWE]+")
_STACK_PROTECTOR_SYMBOL = re.compile(r"__stack_chk_fail(?:_local)?(?:@[^\s]+)?")
_DYNAMIC_TAG = re.compile(r"\((NEEDED|RPATH|RUNPATH)\).*?\[([^\]]*)\]")


class ElfError(Exception):
    """An ELF record is malformed or cannot be safely resolved."""


def machine_report(header: str, expected_machine: str) -> dict[str, object]:
    expected = {
        "x86_64": "Advanced Micro Devices X86-64",
        "aarch64": "AArch64",
    }.get(expected_machine)
    fields = {
        key: next((line.partition(":")[2].strip() for line in header.splitlines()
                   if line.strip().startswith(f"{key}:")), None)
        for key in ("Class", "Machine")
    }
    ok = expected is not None and fields["Class"] == "ELF64" and fields["Machine"] == expected
    return {"ok": ok, "expected_machine": expected_machine, **fields}


def dynamic_tags(dynamic: str) -> dict[str, list[str]]:
    result = {"needed": [], "rpath": [], "runpath": []}
    for line in dynamic.splitlines():
        match = _DYNAMIC_TAG.search(line)
        if match is None:
            continue
        tag, value = match.groups()
        result[{"NEEDED": "needed", "RPATH": "rpath", "RUNPATH": "runpath"}[tag]].append(value)
    return result


def linkage_report(
    root: Path,
    elf: Path,
    *,
    needed: list[str],
    runpaths: list[str],
    system_libraries: set[str],
) -> dict[str, object]:
    root = Path(root).resolve()
    elf = Path(elf).resolve()
    if not elf.is_relative_to(root):
        raise ElfError(f"ELF path escaped product root: {elf}")
    relative = PurePosixPath(elf.relative_to(root).as_posix())
    resolved_paths: list[Path] = []
    violations: list[str] = []
    for raw in runpaths:
        if not raw.startswith("$ORIGIN") or (len(raw) > 7 and raw[7] != "/"):
            violations.append(f"unsafe runpath {raw!r}")
            continue
        stack = list(relative.parent.parts)
        for part in raw[7:].split("/"):
            if part in ("", "."):
                continue
            if part == "..":
                if not stack:
                    violations.append(f"runpath escapes product root: {raw!r}")
                    break
                stack.pop()
            elif "$" in part:
                violations.append(f"unsupported runpath variable in {raw!r}")
                break
            else:
                stack.append(part)
        else:
            directory = root.joinpath(*stack).resolve()
            if not directory.is_relative_to(root) or not directory.is_dir():
                violations.append(f"unresolved runpath {raw!r}")
            else:
                resolved_paths.append(directory)

    missing: list[str] = []
    for library in needed:
        if library in system_libraries:
            continue
        candidates = [directory / library for directory in resolved_paths]
        if not any(
            candidate.is_file() and candidate.resolve().is_relative_to(root)
            for candidate in candidates
        ):
            missing.append(library)
    return {
        "ok": not violations and not missing,
        "needed": needed,
        "runpaths": runpaths,
        "resolved_runpaths": [str(path.relative_to(root)) for path in resolved_paths],
        "missing_product_libraries": missing,
        "runpath_violations": violations,
    }


def gnu_stack_report(program_headers: str) -> dict[str, str | bool | None]:
    """Parse one final ELF's `readelf -lW` PT_GNU_STACK record."""
    records = [
        line.split()
        for line in program_headers.splitlines()
        if line.split() and line.split()[0] in _STACK_TYPES
    ]
    if not records:
        return {
            "present": False,
            "flags": None,
            "executable": None,
            "ok": False,
            "error": "missing PT_GNU_STACK (executable by default on some loaders)",
        }
    if len(records) != 1:
        return {
            "present": True,
            "flags": None,
            "executable": None,
            "ok": False,
            "error": f"expected one PT_GNU_STACK record, found {len(records)}",
        }
    fields = records[0]
    flags = fields[-2] if len(fields) >= 3 else ""
    if _PROGRAM_FLAGS.fullmatch(flags) is None:
        return {
            "present": True,
            "flags": flags or None,
            "executable": None,
            "ok": False,
            "error": f"unrecognized PT_GNU_STACK flags {flags!r}",
        }
    executable = "E" in flags
    return {
        "present": True,
        "flags": flags,
        "executable": executable,
        "ok": not executable,
        "error": "executable stack requested" if executable else None,
    }


def has_stack_protector_reference(dynamic_symbols: str) -> bool:
    """Whether final dynamic symbols include a stack-protector failure call."""
    return any(
        _STACK_PROTECTOR_SYMBOL.fullmatch(symbol) is not None
        for line in dynamic_symbols.splitlines()
        for symbol in line.split()
    )


def hardening_report(
    compiler_flags: str,
    dynamic_symbols: dict[str, str],
) -> dict[str, object]:
    """Check portable clang/musl hardening evidence in a Linux install.

    `_FORTIFY_SOURCE` is implemented by musl headers and compiler builtins;
    unlike glibc it does not require exported `__*_chk` symbols. The configured
    compile flag is therefore the portable fortify evidence. A dynamic
    `__stack_chk_fail` reference in libpython proves stack-protected functions
    survived link-time optimization and stripping. The small launcher is
    reported too, but is allowed to have no guard reference when none of its
    functions meet the compiler's `-fstack-protector-strong` selection rules.
    """
    try:
        tokens = shlex.split(compiler_flags)
    except ValueError:
        tokens = []
    stack_protector_flag = "-fstack-protector-strong" in tokens
    fortify_flag = "-D_FORTIFY_SOURCE=2" in tokens
    references = {
        name: has_stack_protector_reference(output)
        for name, output in dynamic_symbols.items()
    }
    return {
        "configured_flags": {
            "stack_protector_strong": stack_protector_flag,
            "fortify_source_2": fortify_flag,
        },
        "stack_protector_dynamic_references": references,
        "fortify_implementation": "musl headers and compiler builtins; no glibc _chk symbol requirement",
        "ok": (
            stack_protector_flag
            and fortify_flag
            and references.get("libpython", False)
        ),
    }
