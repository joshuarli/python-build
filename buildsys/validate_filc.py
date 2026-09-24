"""Behavior and ABI checks for a relocated Fil-C/musl CPython install.

`run_validation` exercises the bytes being packaged with the pinned Fil-C
compiler. The native extension is built from shipped headers; the negative
extension is built with the ordinary host compiler and must be invisible to
Fil-C's extension loader. A separate child deliberately violates a bound to
prove that loaded Fil-C code still traps.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .filc import FilCToolchain
from .validate_macos import (
    ValidationError, capability_checks, multiprocessing_checks,
    terminal_checks, tls_checks,
)


class FilCValidationError(Exception):
    """A Fil-C qualification probe could not run."""


_EXTENSION = r'''
#include <Python.h>
#include <stdlib.h>

static PyObject *answer(PyObject *self, PyObject *unused) {
    return PyBytes_FromStringAndSize("filc", 4);
}

static PyObject *unsafe_write(PyObject *self, PyObject *unused) {
    volatile char *p = malloc(4);
    if (p == NULL) return PyErr_NoMemory();
    p[16] = 'x';
    free((void *)p);
    Py_RETURN_NONE;
}

static PyMethodDef methods[] = {
    {"answer", answer, METH_NOARGS, NULL},
    {"unsafe_write", unsafe_write, METH_NOARGS, NULL},
    {NULL, NULL, 0, NULL}
};
static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "filc_probe", NULL, -1, methods
};
PyMODINIT_FUNC PyInit_filc_probe(void) { return PyModule_Create(&module); }
'''

_ORDINARY_EXTENSION = r'''
#include <Python.h>
static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "ordinary_probe", NULL, -1, NULL
};
PyMODINIT_FUNC PyInit_ordinary_probe(void) { return PyModule_Create(&module); }
'''

_CTYPES_HELPER = "int filc_helper_answer(void) { return 7; }\n"


def _run(command: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise FilCValidationError(f"timed out: {command[0]}: {error}") from error


def _json_probe(python: Path, code: str) -> dict:
    result = _run([str(python), "-c", code])
    if result.returncode:
        raise FilCValidationError((result.stdout + result.stderr)[-1200:])
    try:
        return json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise FilCValidationError(f"invalid Python probe output: {result.stdout[-500:]}") from error


def core_runtime_checks(python: Path, repo: Path) -> dict:
    """Run the toy and focused runtime scripts with the installed interpreter."""
    results = {}
    for name, script in (
        ("toy", repo / ".github/scripts/toy.py"),
        ("focused", repo / "tests/filc_runtime_smoke.py"),
    ):
        result = _run([str(python), str(script)], timeout=180)
        results[name] = {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "output_tail": (result.stdout + result.stderr)[-1200:],
        }
    results["ok"] = all(value["ok"] for value in results.values())
    return results


def filc_capability_checks(python: Path) -> dict:
    """Exercise the locked native closure and SQLite-backed dbm mapping."""
    result = capability_checks(python, dbm_backend="sqlite3")
    inventory = _json_probe(python, (
        "import importlib.util,json;"
        "print(json.dumps({'bdb_module_absent':"
        "importlib.util.find_spec('_dbm') is None}))"
    ))
    result.update(inventory)
    result["ok"] = (
        result["ok"]
        and result["whichdb"] == "dbm.sqlite3"
        and result["dbm_default"] == ["dbm.sqlite3", True]
        and result["bdb_module_absent"]
    )
    return result


def filc_ctypes_checks(python: Path, locked: FilCToolchain, workdir: Path) -> dict:
    """Call libc, a Fil-C dylib, and a Python callback through libffi."""
    locked.require_ready()
    workdir.mkdir(parents=True, exist_ok=True)
    helper_c = workdir / "filc_ctypes_helper.c"
    helper_so = workdir / "libfilc_ctypes_helper.so"
    helper_c.write_text(_CTYPES_HELPER)
    compiler = locked.prefix / "build/bin/clang"
    build = _run([str(compiler), "-shared", "-fPIC", str(helper_c), "-o", str(helper_so)])
    if build.returncode:
        raise FilCValidationError(f"Fil-C ctypes helper failed: {build.stderr[-1000:]}")
    probe = _json_probe(python, f"""
import ctypes, ctypes.util, json
libc = ctypes.CDLL(None)
runtime_c = ctypes.util.find_library('c')
runtime_m = ctypes.util.find_library('m')
bundled_math = ctypes.CDLL(runtime_m)
bundled_math.cos.argtypes = [ctypes.c_double]
bundled_math.cos.restype = ctypes.c_double
strlen = libc.strlen
strlen.argtypes = [ctypes.c_char_p]
strlen.restype = ctypes.c_size_t
helper = ctypes.CDLL({str(helper_so)!r})
answer = helper.filc_helper_answer
answer.argtypes = []
answer.restype = ctypes.c_int
compare_type = ctypes.CFUNCTYPE(ctypes.c_int,
    ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
calls = []
def compare(left, right):
    calls.append(1)
    return (left[0] > right[0]) - (left[0] < right[0])
callback = compare_type(compare)
values = (ctypes.c_int * 4)(4, 1, 3, 2)
qsort = libc.qsort
qsort.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, compare_type]
qsort.restype = None
qsort(values, 4, ctypes.sizeof(ctypes.c_int), callback)
number = ctypes.c_int(7)
ctypes.memset(ctypes.addressof(number), 0, ctypes.sizeof(number))
chars = ctypes.create_string_buffer(b'filc')
wide_chars = ctypes.create_unicode_buffer('filc')
print(json.dumps({{'libc_call': strlen(b'filc') == 4,
    'private_dylib_call': answer() == 7,
    'callback_calls': len(calls), 'sorted': list(values) == [1, 2, 3, 4],
    'pointer_integer_roundtrip': number.value == 0,
    'char_pointer_roundtrip': ctypes.c_char_p(ctypes.addressof(chars)).value == b'filc',
    'wide_pointer_roundtrip': ctypes.c_wchar_p(ctypes.addressof(wide_chars)).value == 'filc',
    'bundled_library_lookup': runtime_c == runtime_m and runtime_c.endswith('/lib/libc.so')
        and bundled_math.cos(0.0) == 1.0,
    'wide_integer_pointer_mask': ctypes.c_void_p((1 << 128) - 1).value
        == ctypes.c_void_p(-1).value,
    'dllist_unavailable': not hasattr(ctypes.util, 'dllist')}}))
""")
    probe["ok"] = (
        probe["libc_call"] and probe["private_dylib_call"]
        and probe["callback_calls"] > 0 and probe["sorted"]
        and probe["pointer_integer_roundtrip"]
        and probe["char_pointer_roundtrip"]
        and probe["wide_pointer_roundtrip"]
        and probe["bundled_library_lookup"]
        and probe["wide_integer_pointer_mask"]
        and probe["dllist_unavailable"]
    )
    return probe


def extension_checks(install: Path, locked: FilCToolchain, workdir: Path) -> dict:
    """Build/load a Fil-C extension, reject ordinary ABI, and check a trap."""
    locked.require_ready()
    python = install / "bin/python3.14"
    include = install / "include/python3.14"
    if not include.joinpath("Python.h").is_file():
        raise FilCValidationError("packaged CPython headers are missing")
    identity = _json_probe(python, (
        "import importlib.machinery,json,sysconfig;"
        "print(json.dumps({'suffix':sysconfig.get_config_var('EXT_SUFFIX'),"
        "'accepted':importlib.machinery.EXTENSION_SUFFIXES}))"
    ))
    suffix = identity["suffix"]
    expected = ".cpython-314-x86_64-filc-linux-musl.so"
    if suffix != expected or identity["accepted"] != [expected]:
        return {"ok": False, "identity": identity, "expected_suffix": expected}

    workdir.mkdir(parents=True, exist_ok=True)
    source = workdir / "filc_probe.c"
    source.write_text(_EXTENSION)
    module = workdir / ("filc_probe" + suffix)
    filc_cc = locked.prefix / "build/bin/clang"
    compile_filc = _run([
        str(filc_cc), "-shared", "-fPIC", "-O2", f"-I{include}",
        str(source), "-o", str(module),
    ], timeout=180)
    if compile_filc.returncode:
        return {"ok": False, "filc_compile": (compile_filc.stdout + compile_filc.stderr)[-1200:]}
    elf = _run(["readelf", "-d", str(module)])
    symbols = _run(["readelf", "-Ws", str(module)])
    filc_identity = (
        "libpizlo.so" in elf.stdout
        and "pizlonated_PyInit_filc_probe" in symbols.stdout
    )
    call = _json_probe(python, (
        f"import json,sys;sys.path.insert(0,{str(workdir)!r});"
        "import filc_probe;print(json.dumps({'answer':filc_probe.answer().decode()}))"
    ))

    unsafe = _run([
        str(python), "-c",
        f"import sys;sys.path.insert(0,{str(workdir)!r});"
        "import filc_probe;filc_probe.unsafe_write()",
    ])
    trap = unsafe.returncode != 0 and "filc safety error" in (unsafe.stderr + unsafe.stdout)

    ordinary_source = workdir / "ordinary_probe.c"
    ordinary_source.write_text(_ORDINARY_EXTENSION)
    ordinary = workdir / "ordinary_probe.cpython-314-x86_64-linux-musl.so"
    compile_ordinary = _run([
        "cc", "-shared", "-fPIC", f"-I{include}", str(ordinary_source),
        "-o", str(ordinary),
    ])
    if compile_ordinary.returncode:
        return {"ok": False, "ordinary_compile": (compile_ordinary.stdout + compile_ordinary.stderr)[-1200:]}
    negative = _json_probe(python, (
        f"import importlib.util,json,sys;sys.path.insert(0,{str(workdir)!r});"
        "print(json.dumps({'find_spec':importlib.util.find_spec('ordinary_probe') is None}))"
    ))
    result = {
        "identity": identity,
        "filc_elf_identity": filc_identity,
        "extension_call": call.get("answer") == "filc",
        "safety_trap": trap,
        "safety_returncode": unsafe.returncode,
        "safety_diagnostic": (unsafe.stdout + unsafe.stderr)[:250],
        "ordinary_extension_rejected": negative.get("find_spec") is True,
    }
    result["ok"] = all(result[key] for key in (
        "filc_elf_identity", "extension_call", "safety_trap",
        "ordinary_extension_rejected",
    ))
    return result


def run_validation(install: Path, locked: FilCToolchain, workdir: Path, repo: Path) -> dict:
    """Collect focused runtime evidence without mutating the install tree."""
    workdir.mkdir(parents=True, exist_ok=True)
    python = install / "bin/python3.14"
    checks = {}
    probes = (
        ("core_runtime", core_runtime_checks, (python, repo)),
        ("capabilities", filc_capability_checks, (python,)),
        ("ctypes", filc_ctypes_checks, (python, locked, workdir / "ctypes")),
        ("multiprocessing", multiprocessing_checks, (python,)),
        ("terminal", terminal_checks, (python, install)),
        ("tls", tls_checks, (python, workdir)),
        ("extension_abi_safety", extension_checks, (install, locked, workdir / "extension")),
    )
    for name, function, args in probes:
        try:
            checks[name] = function(*args)
        except (FilCValidationError, ValidationError, OSError, ValueError) as error:
            checks[name] = {"ok": False, "error": str(error)}
    failed = sorted(name for name, result in checks.items() if not result.get("ok"))
    return {"checks": checks, "failed": failed, "ok": not failed}
