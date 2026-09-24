"""ELF security properties that can be checked in final package bytes."""

from __future__ import annotations

import re
import shlex

_STACK_TYPES = frozenset({"GNU_STACK", "PT_GNU_STACK"})
_PROGRAM_FLAGS = re.compile(r"[RWE]+")
_STACK_PROTECTOR_SYMBOL = re.compile(r"__stack_chk_fail(?:_local)?(?:@[^\s]+)?")


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
