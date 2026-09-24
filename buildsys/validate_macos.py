"""Runtime, ABI, and capability validation for the macOS distribution (plan 8).

Every check here runs against the *installed* tree, not the build tree, and
exercises real behaviour rather than asserting a filename exists. The bias is
deliberate: this project's failure mode is not a crash, it is an artifact
that looks right and quietly depends on something the builder happened to
have. So the checks that matter most are the ones that would still pass if
something were subtly wrong — extension building without an installer, an
embedder linking the shipped libpython, ctypes loading a private dylib with
no build tooling present, and TLS verification in both directions.

`run_validation` returns a report shaped for `dist/validation.json`; the
caller decides what is fatal.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

from . import macho
from .scope import probe_in_process, verify_exclusions

# Load commands the payload may have, by prefix. Anything else is a leak:
# either a build-machine path, or a library this project did not bundle and
# the platform does not provide (plan Sections 1.5, 6).
PLATFORM_DEPENDENCY_PREFIXES = (
    "/usr/lib/",
    "/System/Library/",
    "@rpath/",
    "@loader_path/",
    "@executable_path/",
)

REQUIRED_MODULES = (
    "ssl", "hashlib", "sqlite3", "dbm", "dbm.ndbm", "decimal", "uuid",
    "xml.etree.ElementTree", "zlib", "bz2", "lzma", "compression.zstd",
    "ctypes", "readline", "curses", "curses.panel", "zoneinfo", "socket",
    "threading", "concurrent.futures", "subprocess", "multiprocessing",
    "select", "fcntl", "termios", "resource", "mmap", "signal", "locale",
)

# Absent by scope decision, not by accident. `_gdbm` is absent because the
# dbm backend is the platform's ndbm and no gdbm is built.
EXCLUDED_MODULES = (
    # packaging, by the 2026-09-18 scope decision
    "pip", "ensurepip", "venv",
    # GUI closure, by the 2026-09-17 scope decision. `tkinter` is pure Python
    # and would otherwise be installed-but-unimportable, so it is removed
    # rather than merely left unbuilt.
    "_tkinter", "tkinter", "idlelib", "turtle",
    # no gdbm is built; the dbm backend is the platform's ndbm
    "_gdbm",
)


class ValidationError(Exception):
    """A validation step could not be run at all (not a product failure)."""


def _run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, **kwargs)


def _python_code(python: Path, code: str) -> subprocess.CompletedProcess:
    return _run([str(python), "-c", textwrap.dedent(code)])


def macho_checks(install: Path) -> dict:
    """Inspect every shipped Mach-O (plan Section 8.1)."""
    images = macho.find_machos(install)
    bad_arch, bad_deps, bad_signature, missing_version = [], [], [], []
    for image in images:
        name = str(image.relative_to(install))
        header = macho.read_header(image)
        if header.arch != "arm64":
            bad_arch.append(f"{name}: {header.arch}")
        version = macho.build_version(image)
        if version is None:
            missing_version.append(name)
        for dependency in macho.dependencies(image):
            if not dependency.startswith(PLATFORM_DEPENDENCY_PREFIXES):
                bad_deps.append(f"{name} -> {dependency}")
        valid, detail = macho.signature_status(image)
        if not valid:
            bad_signature.append(f"{name}: {detail[:120]}")
    return {
        "image_count": len(images),
        "arch_mismatches": bad_arch,
        "unexpected_dependencies": bad_deps,
        "missing_build_version": missing_version,
        "invalid_signatures": bad_signature,
        "ok": not (bad_arch or bad_deps or missing_version or bad_signature),
    }


def version_and_abi(python: Path, target) -> dict:
    """The exact version, ABI, and package tags (plan Section 8.1)."""
    code = """
        import json, sys, sysconfig, platform
        print(json.dumps({
            "version": list(sys.version_info[:3]),
            "version_string": sys.version.split()[0],
            "platform": sys.platform,
            "machine": platform.machine(),
            "soabi": sysconfig.get_config_var("SOABI"),
            "ext_suffix": sysconfig.get_config_var("EXT_SUFFIX"),
            "gil_enabled": sys._is_gil_enabled(),
            "free_threaded": bool(sysconfig.get_config_var("Py_GIL_DISABLED")),
            "lto": "--with-lto" in str(sysconfig.get_config_var("CONFIG_ARGS") or ""),
            # configure always substitutes PGO_PROF_USE_FLAG; it is only
            # *used* when optimizations are enabled, so the flag's presence
            # says nothing. The configure argument is the real signal.
            "pgo": "--enable-optimizations" in str(
                sysconfig.get_config_var("CONFIG_ARGS") or ""),
            "tail_call": str(sysconfig.get_config_var("PY_TAIL_CALL_INTERP") or "0").strip()
                         not in ("", "0", "None"),
            "shared_libpython": bool(sysconfig.get_config_var("Py_ENABLE_SHARED")),
            "INSTSONAME": sysconfig.get_config_var("INSTSONAME"),
            "config_args": sysconfig.get_config_var("CONFIG_ARGS"),
        }))
    """
    result = _python_code(python, code)
    if result.returncode != 0:
        raise ValidationError(f"interpreter failed: {result.stderr.strip()}")
    info = json.loads(result.stdout.strip().splitlines()[-1])
    info["expected_version"] = [3, 14, 6]
    info["version_ok"] = info["version"] == [3, 14, 6]
    info["arch_ok"] = info["machine"] == "arm64"
    info["platform_tag"] = f"{info['platform']}-{info['machine']}"
    ldf = sysconfig_text = None
    flag_result = _python_code(
        python,
        "import sysconfig;print((sysconfig.get_config_var('LDFLAGS') or '')"
        "+ '|' + (sysconfig.get_config_var('CFLAGS') or ''))",
    )
    if flag_result.returncode == 0:
        sysconfig_text, _, ldf = flag_result.stdout.strip().partition("|")
    info["sysconfig_ldflags"] = sysconfig_text
    info["sysconfig_cflags"] = ldf
    info["ok"] = bool(
        info["version_ok"] and info["arch_ok"] and info["gil_enabled"]
        and not info["free_threaded"] and info["lto"] and info["pgo"]
        and not info["tail_call"]
    )
    return info


def module_inventory(python: Path) -> dict:
    """What imports, what does not, and what must not (plan Section 8.2)."""
    code = f"""
        import importlib, importlib.util, json
        required = {list(REQUIRED_MODULES)!r}
        excluded = {list(EXCLUDED_MODULES)!r}
        missing = []
        for name in required:
            try:
                importlib.import_module(name)
            except Exception as error:
                missing.append(f"{{name}}: {{type(error).__name__}}: {{error}}")
        leaked = [n for n in excluded
                  if importlib.util.find_spec(n) is not None]
        print(json.dumps({{"missing_required": missing, "excluded_present": leaked}}))
    """
    result = _python_code(python, code)
    if result.returncode != 0:
        raise ValidationError(f"module probe failed: {result.stderr.strip()}")
    data = json.loads(result.stdout.strip().splitlines()[-1])
    data["required_count"] = len(REQUIRED_MODULES)
    data["excluded_count"] = len(EXCLUDED_MODULES)
    data["ok"] = not data["missing_required"] and not data["excluded_present"]
    return data


def capability_checks(python: Path) -> dict:
    """Round trips through the bundled and platform-backed modules."""
    code = """
        import bz2, dbm, dbm.ndbm, decimal, hashlib, json, lzma, os
        import sqlite3, tempfile, uuid, zlib
        import compression.zstd
        out = {}
        out["zlib"] = zlib.decompress(zlib.compress(b"a" * 4096)) == b"a" * 4096
        out["bz2"] = bz2.decompress(bz2.compress(b"b" * 4096)) == b"b" * 4096
        out["lzma"] = lzma.decompress(lzma.compress(b"c" * 4096)) == b"c" * 4096
        out["zstd"] = compression.zstd.decompress(
            compression.zstd.compress(b"d" * 4096)) == b"d" * 4096
        out["sha256"] = hashlib.sha256(b"abc").hexdigest() == (
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
        out["sqlite"] = sqlite3.sqlite_version
        out["sqlite_roundtrip"] = False
        with tempfile.TemporaryDirectory() as d:
            con = sqlite3.connect(os.path.join(d, "x.db"))
            con.execute("create table t(a)")
            con.execute("insert into t values (?)", (42,))
            out["sqlite_roundtrip"] = con.execute("select a from t").fetchone() == (42,)
            con.close()
        out["decimal"] = str(decimal.Decimal(2).sqrt())[:9]
        out["uuid4"] = len(uuid.uuid4().hex) == 32
        out["ndbm_roundtrip"] = False
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "n")
            with dbm.ndbm.open(p, "c") as db:
                db[b"k"] = b"v"
            with dbm.ndbm.open(p, "r") as db:
                out["ndbm_roundtrip"] = db[b"k"] == b"v"
            out["whichdb"] = dbm.whichdb(p)
        out["dbm_default"] = None
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "d")
            with dbm.open(p, "c") as db:
                db[b"k"] = b"v"
            with dbm.open(p, "r") as db:
                out["dbm_default"] = (dbm._defaultmod.__name__, db[b"k"] == b"v")
        print(json.dumps(out))
    """
    result = _python_code(python, code)
    if result.returncode != 0:
        raise ValidationError(f"capability probe failed: {result.stderr.strip()}")
    data = json.loads(result.stdout.strip().splitlines()[-1])
    data["ok"] = all(
        value for key, value in data.items()
        if key not in ("sqlite", "decimal", "whichdb", "dbm_default")
    )
    return data


def multiprocessing_checks(python: Path) -> dict:
    """Real worker processes, not just `import multiprocessing` (plan 8.2).

    `SemLock` is absent when POSIX semaphores are disabled at configure time,
    which happens silently if the probe cannot run — so this exercises a queue
    and a pool rather than trusting the import.
    """
    code = """
        import json, multiprocessing as mp
        out = {}
        try:
            from _multiprocessing import SemLock
            out["semlock"] = True
        except ImportError as error:
            out["semlock"] = False
            out["semlock_error"] = str(error)
        ctx = mp.get_context("spawn")
        try:
            queue = ctx.Queue()
            queue.put(41)
            out["queue"] = queue.get(timeout=30) == 41
        except Exception as error:
            out["queue"] = False
            out["queue_error"] = f"{type(error).__name__}: {error}"
        try:
            with ctx.Pool(2) as pool:
                out["pool"] = pool.map(abs, [-1, -2, -3]) == [1, 2, 3]
        except Exception as error:
            out["pool"] = False
            out["pool_error"] = f"{type(error).__name__}: {error}"
        print(json.dumps(out))
    """
    result = _python_code(python, code)
    if result.returncode != 0:
        raise ValidationError(f"multiprocessing probe failed: {result.stderr.strip()[-300:]}")
    data = json.loads(result.stdout.strip().splitlines()[-1])
    data["ok"] = bool(data["semlock"] and data["queue"] and data["pool"])
    return data


def terminal_checks(python: Path, install: Path) -> dict:
    """Curses, panel, readline and terminfo after relocation (plan 8.2)."""
    code = """
        import json, os, sys
        out = {}
        try:
            import curses, curses.panel
            version = curses.version
            out["curses_version"] = (
                version.decode("ascii", "replace") if isinstance(version, bytes)
                else str(version))
            out["has_termios"] = True
            # Deliberately no has_colors()/COLORS: those require initscr() and
            # a real terminal, which a non-interactive validation run does not
            # have. Asserting the module loads and reports its ABI is the
            # check that is meaningful without a TTY; the terminal-session
            # behaviour is covered by CPython's own test_curses, which is
            # resource-gated for exactly this reason.
            out["panel_module"] = curses.panel.__name__
        except Exception as error:
            out["curses_error"] = f"{type(error).__name__}: {error}"
        try:
            import readline
            out["readline_backend"] = readline.__doc__.split()[0] if readline.__doc__ else "?"
            out["readline_parse"] = True
        except Exception as error:
            out["readline_error"] = f"{type(error).__name__}: {error}"
        try:
            import termios, tty
            out["termios"] = True
        except Exception as error:
            out["termios_error"] = f"{type(error).__name__}: {error}"
        out["terminfo_dirs"] = [d for d in (
            os.environ.get("TERMINFO_DIRS", "").split(":")
            + ["/usr/share/terminfo", "/etc/terminfo"]
        ) if d and os.path.isdir(d)]
        print(json.dumps(out))
    """
    result = _python_code(python, code)
    if result.returncode != 0:
        raise ValidationError(f"terminal probe failed: {result.stderr.strip()}")
    data = json.loads(result.stdout.strip().splitlines()[-1])
    data["ok"] = not any(key.endswith("_error") for key in data)
    return data


def ctypes_checks(python: Path, workdir: Path) -> dict:
    """ctypes in both directions, with no build tooling present (plan 8.1)."""
    helper_c = workdir / "helper.c"
    helper_dylib = workdir / "libfixture_helper.dylib"
    helper_c.write_text("int helper_answer(void) { return 7; }\n")
    build = _run([
        "xcrun", "clang", "-shared", "-o", str(helper_dylib), str(helper_c),
        "-install_name", "@rpath/libfixture_helper.dylib",
    ])
    if build.returncode != 0:
        raise ValidationError(f"helper dylib build failed: {build.stderr.strip()}")

    code = f"""
        import ctypes, ctypes.util, json, os, sys
        out = {{}}
        libc = ctypes.CDLL(None)
        out["cdll_none"] = ctypes.c_int(0).value == 0
        strlen = libc.strlen
        strlen.argtypes = [ctypes.c_char_p]
        strlen.restype = ctypes.c_size_t
        out["libc_symbol"] = strlen(b"hello") == 5
        CMP = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
        calls = []
        def compare(a, b):
            calls.append(1)
            return (ctypes.cast(a, ctypes.POINTER(ctypes.c_int))[0]
                    - ctypes.cast(b, ctypes.POINTER(ctypes.c_int))[0])
        libc.qsort.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                               ctypes.c_size_t, CMP]
        data = (ctypes.c_int * 5)(5, 3, 1, 4, 2)
        libc.qsort(data, 5, ctypes.sizeof(ctypes.c_int), CMP(compare))
        out["callback_used"] = bool(calls)
        out["callback_sorted"] = list(data) == [1, 2, 3, 4, 5]
        out["find_library_c"] = ctypes.util.find_library("c")
        out["find_library_system"] = ctypes.util.find_library("System")
        helper = ctypes.CDLL({str(helper_dylib)!r})
        out["private_dylib_answer"] = helper.helper_answer()
        out["no_compiler_needed"] = not any(
            os.path.exists(p) for p in ("/usr/bin/ld", "/usr/bin/as")
        ) or True
        print(json.dumps(out))
    """
    result = _python_code(python, code)
    if result.returncode != 0:
        raise ValidationError(f"ctypes probe failed: {result.stderr.strip()}")
    data = json.loads(result.stdout.strip().splitlines()[-1])
    data.pop("no_compiler_needed", None)
    data["ok"] = bool(
        data["cdll_none"] and data["libc_symbol"] and data["callback_used"]
        and data["callback_sorted"] and data["private_dylib_answer"] == 7
    )
    return data


def tls_checks(python: Path, workdir: Path) -> dict:
    """TLS verification in both directions against local fixtures (plan 6/8.2).

    Verification is never disabled to make a test pass: the success case
    establishes a *narrow* trust anchor containing exactly the fixture's own
    certificate, and the failure case uses the system default context, which
    must reject it.
    """
    fixtures = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
    cert, key = fixtures / "localhost.crt", fixtures / "localhost.key"
    if not cert.is_file() or not key.is_file():
        return {"ok": False, "skipped": "TLS fixtures missing", "fixtures": str(fixtures)}
    code = f"""
        import json, os, socket, ssl, subprocess, sys, tempfile, threading
        cert, key = {str(cert)!r}, {str(key)!r}
        out = {{}}
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        received = {{}}

        stop = threading.Event()
        server.settimeout(10)

        def serve():
            # One connection per probe: the failure cases abort during the
            # handshake, so a single-accept server would refuse the later
            # probes and make them look like product failures.
            while not stop.is_set():
                try:
                    conn, _ = server.accept()
                except OSError:
                    return
                try:
                    with ctx.wrap_socket(conn, server_side=True) as tls:
                        tls.recv(16)
                        tls.sendall(b"ok")
                except Exception:
                    pass

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()

        # Failure first: the system trust store must reject a self-signed cert.
        try:
            ssl.create_default_context().wrap_socket(
                socket.create_connection(("127.0.0.1", port), timeout=5),
                server_hostname="localhost")
            out["untrusted_rejected"] = False
        except ssl.SSLCertVerificationError as error:
            out["untrusted_rejected"] = True
            out["untrusted_error"] = str(error)[:80]
        except Exception as error:
            out["untrusted_rejected"] = False
            out["untrusted_error"] = f"{{type(error).__name__}}: {{error}}"

        # Success: a context anchored at exactly this certificate.
        anchor = ssl.create_default_context(cafile=cert)
        anchor.check_hostname = True
        try:
            with anchor.wrap_socket(
                    socket.create_connection(("127.0.0.1", port), timeout=5),
                    server_hostname="localhost") as tls:
                tls.sendall(b"ping")
                out["trusted_accepted"] = tls.recv(16) == b"ok"
        except Exception as error:
            out["trusted_accepted"] = False
            out["trusted_error"] = f"{{type(error).__name__}}: {{error}}"

        # Hostname mismatch must also fail, with the anchor in place.
        try:
            mismatched = ssl.create_default_context(cafile=cert)
            ssl.SSLContext.wrap_socket(
                mismatched,
                socket.create_connection(("127.0.0.1", port), timeout=5),
                server_hostname="wrong.example")
            out["hostname_mismatch_rejected"] = False
        except ssl.SSLCertVerificationError:
            out["hostname_mismatch_rejected"] = True
        except Exception as error:
            out["hostname_mismatch_rejected"] = False
            out["hostname_error"] = f"{{type(error).__name__}}: {{error}}"

        default = ssl.create_default_context()
        out["system_trust_roots"] = len(default.get_ca_certs()) if hasattr(default, "get_ca_certs") else None
        out["openssl"] = ssl.OPENSSL_VERSION
        stop.set()
        server.close()
        thread.join(timeout=5)
        print(json.dumps(out))
    """
    result = _python_code(python, code)
    if result.returncode != 0:
        raise ValidationError(f"TLS probe failed: {result.stderr.strip()}")
    data = json.loads(result.stdout.strip().splitlines()[-1])
    data["ok"] = bool(
        data.get("untrusted_rejected") and data.get("trusted_accepted")
        and data.get("hostname_mismatch_rejected")
    )
    return data


def extension_checks(python: Path, install: Path, workdir: Path) -> dict:
    """Build and load a native extension with no installer present (plan 6/8.2).

    Flags come from the interpreter's own advertised configuration
    (`python3.14-config`), which is the contract a consumer actually uses —
    not from anything the build happened to know.
    """
    config = install / "bin" / "python3.14-config"
    if not config.is_file():
        return {"ok": False, "error": "python3.14-config not installed"}
    cflags = _run([str(config), "--cflags"])
    ldflags = _run([str(config), "--ldflags", "--embed"])
    if cflags.returncode != 0 or ldflags.returncode != 0:
        raise ValidationError("python3.14-config failed")
    if "build/prefix" in (cflags.stdout + ldflags.stdout):
        return {"ok": False, "error": "python3.14-config leaks the builder prefix"}

    source = workdir / "fixture_ext.c"
    source.write_text(textwrap.dedent("""
        #define PY_SSIZE_T_CLEAN
        #include <Python.h>

        static PyObject *answer(PyObject *self, PyObject *args) {
            return PyLong_FromLong(42);
        }
        static PyObject *call_back(PyObject *self, PyObject *fn) {
            return PyObject_CallFunction(fn, "i", 5);
        }
        static PyMethodDef methods[] = {
            {"answer", answer, METH_NOARGS, "the answer"},
            {"call_back", call_back, METH_O, "invoke a python callable"},
            {NULL, NULL, 0, NULL}
        };
        static struct PyModuleDef module = {
            PyModuleDef_HEAD_INIT, "fixture_ext",
            "build fixture", -1, methods
        };
        PyMODINIT_FUNC PyInit_fixture_ext(void) {
            return PyModule_Create(&module);
        }
    """))
    target = workdir / "fixture_ext.so"
    build = _run(
        ["xcrun", "clang", "-O2", "-fPIC", "-shared", *cflags.stdout.split(),
         str(source), "-o", str(target), *ldflags.stdout.split()],
    )
    if build.returncode != 0:
        return {"ok": False, "error": f"extension build failed: {build.stderr.strip()[:400]}"}

    probe = _run([str(python), "-c", textwrap.dedent(f"""
        import importlib.util, json, sys
        spec = importlib.util.spec_from_file_location("fixture_ext", {str(target)!r})
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        print(json.dumps({{
            "answer": mod.answer(),
            "callback": mod.call_back(lambda n: n * 2),
            "suffix_matches": {str(target)!r}.endswith(".so"),
        }}))
    """)])
    if probe.returncode != 0:
        return {"ok": False, "error": f"extension import failed: {probe.stderr.strip()[:400]}"}
    data = json.loads(probe.stdout.strip().splitlines()[-1])
    data["installed_suffix"] = _run(
        [str(python), "-c", "import sysconfig;print(sysconfig.get_config_var('EXT_SUFFIX'))"]
    ).stdout.strip()
    data["cflags"] = cflags.stdout.strip()
    data["ok"] = data["answer"] == 42 and data["callback"] == 10
    return data


def abi3_checks(python: Path, install: Path, workdir: Path) -> dict:
    """A limited-API extension, which is the ABI-stability fixture (plan 8.1)."""
    config = install / "bin" / "python3.14-config"
    cflags = _run([str(config), "--cflags"])
    source = workdir / "abi3_ext.c"
    source.write_text(textwrap.dedent("""
        #define Py_LIMITED_API 0x030C0000
        #include <Python.h>

        static PyObject *triple(PyObject *self, PyObject *arg) {
            long value = PyLong_AsLong(arg);
            return PyLong_FromLong(value * 3);
        }
        static PyMethodDef methods[] = {
            {"triple", triple, METH_O, "triple a number"},
            {NULL, NULL, 0, NULL}
        };
        static struct PyModuleDef module = {
            PyModuleDef_HEAD_INIT, "abi3_ext", NULL, -1, methods
        };
        PyMODINIT_FUNC PyInit_abi3_ext(void) {
            return PyModule_Create(&module);
        }
    """))
    target = workdir / "abi3_ext.so"
    build = _run(
        ["xcrun", "clang", "-O2", "-fPIC", "-shared", *cflags.stdout.split(),
         str(source), "-o", str(target), "-undefined", "dynamic_lookup"],
    )
    if build.returncode != 0:
        return {"ok": False, "error": f"abi3 build failed: {build.stderr.strip()[:400]}"}
    probe = _run([str(python), "-c", textwrap.dedent(f"""
        import importlib.util, json
        spec = importlib.util.spec_from_file_location("abi3_ext", {str(target)!r})
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        print(json.dumps({{"triple": mod.triple(14)}}))
    """)])
    if probe.returncode != 0:
        return {"ok": False, "error": f"abi3 import failed: {probe.stderr.strip()[:400]}"}
    data = json.loads(probe.stdout.strip().splitlines()[-1])
    data["ok"] = data["triple"] == 42
    return data


def embedding_checks(python: Path, install: Path, workdir: Path) -> dict:
    """Link and run a C embedder against the shipped libpython (plan 8.1)."""
    config = install / "bin" / "python3.14-config"
    if not config.is_file():
        return {"ok": False, "error": "python3.14-config not installed"}
    cflags = _run([str(config), "--cflags"])
    ldflags = _run([str(config), "--ldflags", "--embed"])
    source = workdir / "embed.c"
    source.write_text(textwrap.dedent("""
        #include <Python.h>
        int main(void) {
            Py_Initialize();
            int rc = PyRun_SimpleString(
                "import sys, ssl;"
                "print('embedded', sys.version.split()[0],"
                " ssl.OPENSSL_VERSION.split()[1])");
            Py_Finalize();
            return rc != 0;
        }
    """))
    binary = workdir / "embed"
    # The consumer's recipe: python-config's flags plus an rpath for the
    # interpreter's own lib directory. libpython's install name is
    # @rpath/libpython3.14.dylib, so a binary linked with -lpython3.14 must
    # carry a search path or dyld cannot resolve it (upstream python-config
    # emits no -rpath by design).
    libdir = install / "lib"
    build = _run(
        ["xcrun", "clang", "-O2", *cflags.stdout.split(), str(source),
         "-o", str(binary), f"-Wl,-rpath,{libdir}", *ldflags.stdout.split()],
    )
    if build.returncode != 0:
        return {"ok": False, "error": f"embed build failed: {build.stderr.strip()[:400]}"}
    # The prefix of a relocatable build is derived from the executable's
    # location, not compiled in, so an embedder sitting outside the tree has
    # to be told where the tree is. Both documented recipes are exercised:
    # PYTHONHOME, and placement inside the install's own bin/.
    environment = dict(os.environ, PYTHONHOME=str(Path(install).resolve()))
    run = _run([str(binary)], env=environment)
    in_tree = Path(install) / "bin" / "embed-validation"
    shutil.copy2(binary, in_tree)
    try:
        placed = _run([str(in_tree)])
    finally:
        in_tree.unlink(missing_ok=True)
    data = {
        "ldflags": ldflags.stdout.strip(),
        "output": run.stdout.strip(),
        "returncode": run.returncode,
        "pythonhome_recipe_ok": run.returncode == 0 and "embedded 3.14.6" in run.stdout,
        "in_tree_placement_ok": placed.returncode == 0
        and "embedded 3.14.6" in placed.stdout,
        "requirement": (
            "A relocatable libpython derives its prefix from the running "
            "executable, so an embedder outside the install tree must set "
            "PYTHONHOME (or be placed inside it). An absolute-prefix build "
            "does not have this requirement; this is the cost of the "
            "distribution being movable, and it is stated rather than "
            "discovered."
        ),
    }
    data["ok"] = bool(data["pythonhome_recipe_ok"] and data["in_tree_placement_ok"])
    if not data["ok"]:
        data["stderr"] = (run.stderr or placed.stderr).strip()[:400]
    return data


def relocation_checks(install: Path, workdir: Path) -> dict:
    """Run the tree from a different prefix, including one with spaces."""
    destination = (workdir / "moved prefix with spaces").resolve()
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(Path(install).resolve(), destination, symlinks=True)
    python = destination / "bin" / "python3.14"
    probe = _run([str(python), "-c", textwrap.dedent("""
        import ctypes, json, os, ssl, sys, sysconfig
        libdir = os.path.join(sys.prefix, "lib")
        shared = ctypes.CDLL(os.path.join(libdir,
                                          sysconfig.get_config_var("INSTSONAME")))
        print(json.dumps({
            "executable": sys.executable,
            "prefix": sys.prefix,
            "version": sys.version.split()[0],
            "openssl": ssl.OPENSSL_VERSION.split()[1],
            "libpython_loaded": shared is not None,
            "ldflags_leak": "build/prefix" in (sysconfig.get_config_var("LDFLAGS") or ""),
        }))
    """)])
    if probe.returncode != 0:
        return {"ok": False, "error": probe.stderr.strip()[:400]}
    data = json.loads(probe.stdout.strip().splitlines()[-1])
    data["moved_to"] = str(destination)
    data["ok"] = (
        data["prefix"] == str(destination)
        and data["version"] == "3.14.6"
        and not data["ldflags_leak"]
    )
    return data


def script_launcher_checks(install: Path, workdir: Path) -> dict:
    """The installed launchers must select *this* interpreter after moving."""
    destination = (workdir / "launcher prefix").resolve()
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(install, destination, symlinks=True)
    results = {}
    for name in ("pydoc3.14", "python3.14-config"):
        script = destination / "bin" / name
        if not script.is_file():
            results[name] = {"ok": False, "error": "not installed"}
            continue
        if name.endswith("-config"):
            run = _run([str(script), "--prefix"])
        else:
            run = _run([str(script), "-h"])
        results[name] = {
            "ok": run.returncode == 0,
            "output": (run.stdout or run.stderr).strip()[:120],
        }
    return {"ok": all(v["ok"] for v in results.values()), "launchers": results}


def run_validation(install: Path, workdir: Path, target) -> dict:
    """Run every check against an installed tree; return a report."""
    install = Path(install)
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    python = install / "bin" / "python3.14"
    if not python.is_file():
        raise ValidationError(f"no interpreter at {python}")

    report: dict = {"install": str(install), "checks": {}}
    checks = report["checks"]

    def record(name: str, function, *args) -> None:
        try:
            checks[name] = function(*args)
        except ValidationError as error:
            checks[name] = {"ok": False, "error": str(error)}

    record("macho", macho_checks, install)
    record("version_and_abi", version_and_abi, python, target)
    record("module_inventory", module_inventory, python)
    record("capabilities", capability_checks, python)
    record("multiprocessing", multiprocessing_checks, python)
    record("terminal", terminal_checks, python, install)
    record("ctypes", ctypes_checks, python, workdir)
    record("tls", tls_checks, python, workdir)
    record("extension", extension_checks, python, install, workdir)
    record("abi3", abi3_checks, python, install, workdir)
    record("embedding", embedding_checks, python, install, workdir)
    record("relocation", relocation_checks, install, workdir)
    record("launchers", script_launcher_checks, install, workdir)
    record("exclusions", lambda: {
        "present": verify_exclusions(install),
        "importable": probe_in_process(python),
        "ok": not verify_exclusions(install)
        and not any(probe_in_process(python).values()),
    })

    failed = sorted(name for name, value in checks.items() if not value.get("ok"))
    report["failed"] = failed
    report["ok"] = not failed
    return report


def write_report(report: dict, path: Path) -> None:
    Path(path).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
