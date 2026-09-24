"""Runtime checks adapted from PBS distribution behavior tests.

The probe tests the PBS compatibility surface supported by this project. It
does not execute or import PBS code. Deliberate scope exclusions and features
only applicable to Windows or glibc are listed in the report rather than
silently counted as passing.
"""

from __future__ import annotations

import json
import os
import pty
import shlex
import select
import signal
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .targets import Target


class CompatibilityError(Exception):
    """A packaged interpreter could not run the compatibility probes."""


def _compatibility_status(result: dict) -> str:
    """Honor both explicit statuses and the probe helpers' boolean results."""
    return (
        "failed"
        if result.get("status") == "failed" or result.get("ok") is False
        else "passed"
    )


_RUNTIME_PROBE = r'''
import ctypes
import hashlib
import importlib.machinery
import json
import os
import platform
import sqlite3
import struct
import sys
import sysconfig
import threading


class SkipCheck(Exception):
    pass


checks = {}


def check(name, function):
    try:
        checks[name] = {"status": "passed", "evidence": function()}
    except SkipCheck as error:
        checks[name] = {"status": "skipped", "reason": str(error)}
    except Exception as error:
        checks[name] = {
            "status": "failed",
            "error": f"{type(error).__name__}: {error}",
        }


def compression():
    import bz2
    import lzma
    import zlib

    assert lzma.is_check_supported(lzma.CHECK_CRC64)
    assert lzma.is_check_supported(lzma.CHECK_SHA256)
    for module in (bz2, lzma, zlib):
        data = b"python-build standalone compression probe"
        assert module.decompress(module.compress(data)) == data
    return "bz2, lzma CRC64/SHA256, and zlib round trips"


def ctypes_callbacks():
    assert ctypes.pythonapi is not None
    libc = ctypes.CDLL(None)
    callback_type = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
    calls = []

    def compare(left, right):
        calls.append(True)
        left_value = ctypes.cast(left, ctypes.POINTER(ctypes.c_int))[0]
        right_value = ctypes.cast(right, ctypes.POINTER(ctypes.c_int))[0]
        return left_value - right_value

    values = (ctypes.c_int * 5)(5, 3, 1, 4, 2)
    libc.qsort(
        values, len(values), ctypes.sizeof(ctypes.c_int), callback_type(compare)
    )
    assert calls and list(values) == [1, 2, 3, 4, 5]
    return "pythonapi and libc qsort callback"


def hashlib_algorithms():
    wanted = {
        "blake2b", "blake2s", "md5", "md5-sha1", "ripemd160", "sha1",
        "sha224", "sha256", "sha384", "sha3_224", "sha3_256",
        "sha3_384", "sha3_512", "sha512", "sha512_224", "sha512_256",
        "shake_128", "shake_256", "sm3",
    }
    missing = wanted - hashlib.algorithms_available
    assert not missing, f"missing algorithms: {sorted(missing)}"
    return sorted(wanted)


def test_capi_modules():
    import _testcapi

    assert _testcapi is not None
    if sys.version_info[:2] >= (3, 13):
        import _testlimitedcapi

        assert _testlimitedcapi is not None
    return "_testcapi and _testlimitedcapi"


def sqlite_features():
    expected_version = tuple(
        int(part) for part in os.environ["EXPECTED_SQLITE_VERSION_INFO"].split(",")
    )
    assert sqlite3.sqlite_version_info == expected_version, (
        f"expected SQLite {expected_version}, got {sqlite3.sqlite_version_info}"
    )
    connection = sqlite3.connect(":memory:")
    assert hasattr(connection, "enable_load_extension")
    assert hasattr(connection, "backup")
    assert hasattr(connection, "serialize")
    connection.enable_load_extension(True)
    connection.enable_load_extension(False)

    cursor = connection.cursor()
    for extension in ("fts3", "fts4", "fts5", "geopoly", "rtree"):
        cursor.execute(
            f"CREATE VIRTUAL TABLE test_{extension} USING {extension}(a, b, c)"
        )
    assert cursor.execute("SELECT COUNT(*) FROM dbstat").fetchone()[0] > 0
    cursor.execute("INSERT INTO test_fts3 VALUES('hello world', '', '')")
    assert cursor.execute(
        "SELECT COUNT(*) FROM test_fts3 WHERE a MATCH 'hello AND world'"
    ).fetchone()[0] == 1
    assert connection.serialize()[:15] == b"SQLite format 3"

    wild_pointer = struct.pack("P", 0xDEADBEEF)
    try:
        cursor.execute(
            f"SELECT fts3_tokenizer('mytokenizer', x'{wild_pointer.hex()}')"
        )
    except sqlite3.OperationalError as error:
        assert str(error) == "fts3tokenize disabled"
    else:
        raise AssertionError("fts3_tokenizer accepted an unbound pointer")
    cursor.execute(
        "SELECT fts3_tokenizer('mytokenizer', ?)", (wild_pointer,)
    )
    return {"sqlite_version": sqlite3.sqlite_version, "virtual_tables": 5}


def ssl_capabilities():
    import ssl

    assert all((ssl.HAS_TLSv1, ssl.HAS_TLSv1_1, ssl.HAS_TLSv1_2, ssl.HAS_TLSv1_3))
    expected_version = tuple(
        int(part) for part in os.environ["EXPECTED_OPENSSL_VERSION_INFO"].split(",")
    )
    assert ssl.OPENSSL_VERSION_INFO == expected_version, (
        f"expected OpenSSL {expected_version}, got {ssl.OPENSSL_VERSION_INFO}"
    )
    ssl.create_default_context()
    return {
        "version": ssl.OPENSSL_VERSION,
        "version_info": ssl.OPENSSL_VERSION_INFO,
    }


def zstd_multithreading():
    from compression import zstd

    upper = zstd.CompressionParameter.nb_workers.bounds()[1]
    assert upper > 0, f"zstd reports maximum worker count {upper}"
    payload = bytes(range(256)) * 8192
    compressor = zstd.ZstdCompressor(
        options={zstd.CompressionParameter.nb_workers: min(2, upper)}
    )
    compressed = compressor.compress(payload) + compressor.flush()
    assert zstd.decompress(compressed) == payload
    return {"max_workers": upper, "roundtrip_bytes": len(payload)}


def gil_and_hash_policy():
    assert sys._is_gil_enabled()
    assert sysconfig.get_config_var("Py_GIL_DISABLED") == 0
    assert sys.hash_info.algorithm.startswith("siphash")
    return {
        "gil_enabled": True,
        "hash_algorithm": sys.hash_info.algorithm,
    }


def target_abi():
    target = os.environ["TARGET_TRIPLE"]
    soabi = sysconfig.get_config_var("SOABI") or ""
    multiarch = getattr(sys.implementation, "_multiarch", "")
    suffix = importlib.machinery.EXTENSION_SUFFIXES[0]
    if target.endswith("-linux-musl"):
        for value in (soabi, multiarch, suffix):
            assert "musl" in value, f"{value!r} does not identify musl"
            assert "gnu" not in value, f"{value!r} identifies glibc"
    elif target.endswith("-apple-darwin"):
        assert sys.platform == "darwin"
        assert platform.machine() == "arm64"
        assert "darwin" in soabi and "darwin" in suffix
    else:
        raise AssertionError(f"unexpected supported target {target!r}")
    return {"soabi": soabi, "multiarch": multiarch, "extension_suffix": suffix}


def linux_uapi_sysconfig():
    if not sys.platform.startswith("linux"):
        raise SkipCheck("Linux-only PBS check")
    for key, value in sysconfig.get_config_vars().items():
        if isinstance(value, str):
            assert "linux-uapi" not in value, f"{key} contains a build-only UAPI path"
    return "no linux-uapi paths in sysconfig"


def linux_mdwe_thread_creation():
    if not sys.platform.startswith("linux"):
        raise SkipCheck("Linux-only PBS check")

    libc = ctypes.CDLL(None, use_errno=True)
    prctl = libc.prctl
    prctl.restype = ctypes.c_int
    pr_get_mdwe = 66
    pr_set_mdwe = 65
    refuse_exec_gain = 1 << 0
    no_inherit = 1 << 1
    mode = prctl(pr_get_mdwe, 0, 0, 0, 0)
    if mode < 0:
        raise SkipCheck("kernel does not support PR_GET_MDWE")
    if not (mode & refuse_exec_gain):
        if prctl(pr_set_mdwe, refuse_exec_gain | no_inherit, 0, 0, 0) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))

    observed = []
    thread = threading.Thread(target=observed.append, args=("worker ran",))
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive(), "thread did not finish under MDWE"
    assert observed == ["worker ran"]
    return "Python thread creation under MemoryDenyWriteExecute"


for name, function in (
    ("compression", compression),
    ("ctypes_callbacks", ctypes_callbacks),
    ("hashlib_algorithms", hashlib_algorithms),
    ("testcapi_modules", test_capi_modules),
    ("sqlite_features", sqlite_features),
    ("ssl_capabilities", ssl_capabilities),
    ("zstd_multithreading", zstd_multithreading),
    ("gil_and_hash_policy", gil_and_hash_policy),
    ("target_abi", target_abi),
    ("linux_uapi_sysconfig", linux_uapi_sysconfig),
    ("linux_mdwe_thread_creation", linux_mdwe_thread_creation),
):
    check(name, function)

not_applicable = {
    "ssl_keylogfile": "PBS-specific regression applies to Windows only",
    "venv_path_resolution": "venv is intentionally excluded; interpreter symlinks are tested separately",
    "tkinter": "GUI support is intentionally excluded and checked by scope validation",
    "linux_gnu_syscalls": "the PBS checks are glibc-only; this project targets musl",
}
print(json.dumps({
    "checks": checks,
    "not_applicable": not_applicable,
    "ok": not any(result["status"] == "failed" for result in checks.values()),
}, sort_keys=True))
'''

_GETPATH_PROBE = "print(42)"
_PREFIX_PROBE = "import pathlib, sys; print(pathlib.Path(sys.prefix).resolve())"
_CURSES_TTY_PROBE = (
    "import curses; curses.initscr(); curses.endwin(); print('PBS_TTY_OK')"
)


def _isolated_environment(target: Target) -> dict[str, str]:
    environment = os.environ.copy()
    for name in tuple(environment):
        if name.startswith("PYTHON"):
            environment.pop(name)
    environment["TARGET_TRIPLE"] = target.triple
    environment["TERM"] = "xterm"
    terminfo = [
        path
        for path in ("/etc/terminfo", "/lib/terminfo", "/usr/share/terminfo")
        if Path(path).is_dir()
    ]
    if terminfo:
        environment["TERMINFO_DIRS"] = ":".join(terminfo)
    return environment


def _getpath_check(python: Path, install: Path, environment: dict[str, str]) -> dict:
    expected_prefix = install.resolve()
    with tempfile.TemporaryDirectory(prefix="standalone-symlink-") as temporary:
        symlink = Path(temporary) / "python"
        symlink.symlink_to(python.resolve())
        result = subprocess.run(
            [str(symlink), "-c", _GETPATH_PROBE],
            cwd=temporary,
            env=environment,
            capture_output=True,
            text=True,
            timeout=15,
        )
    if result.returncode != 0 or result.stdout.strip() != "42":
        raise CompatibilityError(
            "interpreter symlink did not start successfully: "
            f"returncode={result.returncode}, output={result.stdout.strip()!r}, "
            f"stderr={result.stderr.strip()[-500:]}"
        )

    unusual_argv = subprocess.run(
        ["/dev/null", "-c", _GETPATH_PROBE],
        executable=str(python),
        cwd=install,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if unusual_argv.returncode != 0 or unusual_argv.stdout.strip() != "42":
        raise CompatibilityError(
            "interpreter failed with an unusual argv[0]: "
            f"returncode={unusual_argv.returncode}, "
            f"output={unusual_argv.stdout.strip()!r}, "
            f"stderr={unusual_argv.stderr.strip()[-500:]}"
        )
    prefix_result = subprocess.run(
        [str(python), "-I", "-B", "-c", _PREFIX_PROBE],
        cwd=install,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    actual_prefix = (
        Path(prefix_result.stdout.strip()).resolve()
        if prefix_result.stdout.strip()
        else None
    )
    if prefix_result.returncode != 0 or actual_prefix != expected_prefix:
        raise CompatibilityError(
            "interpreter prefix did not resolve from the packaged executable: "
            f"returncode={prefix_result.returncode}, prefix={actual_prefix}, "
            f"stderr={prefix_result.stderr.strip()[-500:]}"
        )
    return {
        "status": "passed",
        "evidence": "external symlink and unusual argv[0] start; sys.prefix resolves",
    }


def _relocated_sysconfig_check(
    python: Path, install: Path, environment: dict[str, str]
) -> dict:
    """Move the complete tree and require sysconfig tools to follow it."""
    with tempfile.TemporaryDirectory(prefix="standalone moved ") as temporary:
        destination = Path(temporary) / "python install with spaces"
        shutil.copytree(Path(install).resolve(), destination, symlinks=True)
        moved_python = destination / "bin" / "python3.14"
        probe = subprocess.run(
            [str(moved_python), "-I", "-B", "-c", r'''
import json, os, sys, sysconfig
root = os.path.realpath(sys.prefix)
import ssl
fallback_bundle = os.path.realpath(ssl._PYTHON_BUILD_DEFAULT_CA_BUNDLE)
default_verify_paths = ssl.SSLContext.set_default_verify_paths
ssl.SSLContext.set_default_verify_paths = lambda self: None
try:
    fallback_context = ssl.create_default_context()
    fallback_ca_count = fallback_context.cert_store_stats()["x509_ca"]
finally:
    ssl.SSLContext.set_default_verify_paths = default_verify_paths
fallback_ca = {
    "bundle": fallback_bundle,
    "inside_moved_tree": os.path.commonpath((root, fallback_bundle)) == root,
    "exists": os.path.isfile(fallback_bundle),
    "ca_count_without_system_store": fallback_ca_count,
    "ok": (
        os.path.commonpath((root, fallback_bundle)) == root
        and os.path.isfile(fallback_bundle) and fallback_ca_count > 0
    ),
}
keys = (
    "BINDIR", "BINLIBDEST", "LIBDIR", "LIBPL", "DESTSHARED", "INCLUDEPY",
    "CONFINCLUDEPY", "LIBDEST", "EXENAME", "prefix", "exec_prefix",
    "base", "base_prefix",
)
values = {key: sysconfig.get_config_var(key) for key in keys}
values = {key: value for key, value in values.items() if value}
def inside(path):
    return os.path.commonpath((root, os.path.realpath(path))) == root
paths = sysconfig.get_paths()
rooted = all(inside(value) for value in paths.values())
rooted = rooted and all(inside(value) for value in values.values())
forbidden = (
    "/install", "/build/prefix", "/.cache/llvm/", "/Python-3.14.6/",
    "code.profclangd", "code-%p.profclangr", "-fprofile-instr-use=",
    "LLVM_PROFILE_FILE=",
)
stale = [f"{key}={value}" for key, value in sysconfig.get_config_vars().items()
         if isinstance(value, str) and any(marker in value for marker in forbidden)]
print(json.dumps({"prefix": sys.prefix, "paths": values, "rooted": rooted, "stale": stale, "fallback_ca": fallback_ca}))
'''],
            cwd=destination,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        try:
            data = json.loads(probe.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError) as error:
            raise CompatibilityError(
                "moved sysconfig probe returned no report: "
                f"returncode={probe.returncode}, stderr={probe.stderr.strip()[-500:]}"
            ) from error
        config = destination / "bin" / "python3.14-config"
        outputs = {
            option: subprocess.run(
                [str(config), *arguments],
                cwd=destination,
                env=environment,
                capture_output=True,
                text=True,
                timeout=15,
            )
            for option, arguments in (
                ("prefix", ["--prefix"]),
                ("configdir", ["--configdir"]),
                ("cflags", ["--cflags"]),
                ("ldflags", ["--ldflags", "--embed"]),
            )
        }
        include_flags = (
            shlex.split(outputs["cflags"].stdout)
            if outputs["cflags"].returncode == 0 else []
        )
        link_flags = (
            shlex.split(outputs["ldflags"].stdout)
            if outputs["ldflags"].returncode == 0 else []
        )
        resolved_destination = destination.resolve()
        prefix_ok = (
            outputs["prefix"].returncode == 0
            and Path(outputs["prefix"].stdout.strip()).resolve() == destination.resolve()
        )
        configdir_ok = (
            outputs["configdir"].returncode == 0
            and Path(outputs["configdir"].stdout.strip()).resolve().is_relative_to(destination.resolve())
        )
        flags_ok = (
            outputs["cflags"].returncode == 0
            and f"-I{resolved_destination / 'include' / 'python3.14'}" in include_flags
            and outputs["ldflags"].returncode == 0
            and f"-L{resolved_destination / 'lib'}" in link_flags
        )
        data.update({
            "moved_to": str(destination),
            "config_prefix": outputs["prefix"].stdout.strip(),
            "configdir": outputs["configdir"].stdout.strip(),
            "cflags": outputs["cflags"].stdout.strip(),
            "ldflags": outputs["ldflags"].stdout.strip(),
            "ok": (
                probe.returncode == 0 and data["rooted"] and not data["stale"]
                and data["fallback_ca"]["ok"]
                and prefix_ok and configdir_ok and flags_ok
            ),
        })
        if probe.stderr.strip():
            data["stderr"] = probe.stderr.strip()[-1000:]
        return data


def _fallback_ca_check(
    python: Path, install: Path, environment: dict[str, str]
) -> dict:
    """Exercise CA fallback, explicit SSL_CERT_FILE, and the opt-out by TLS."""
    fixtures = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
    certificate = fixtures / "localhost.crt"
    key = fixtures / "localhost.key"
    if not certificate.is_file() or not key.is_file():
        return {"ok": False, "error": "local TLS fixtures are missing"}

    code = r'''
import json, os, socket, ssl, sys, tempfile, threading
certificate, key = sys.argv[1:]
original_bundle = ssl._PYTHON_BUILD_DEFAULT_CA_BUNDLE
original_default_paths = ssl.SSLContext.set_default_verify_paths

def tls_roundtrip(context):
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.load_cert_chain(certificate, key)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    failures = []
    def serve():
        try:
            connection, _ = listener.accept()
            with server.wrap_socket(connection, server_side=True) as secure:
                secure.sendall(secure.recv(64))
        except Exception as error:
            failures.append(repr(error))
    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        with socket.create_connection(listener.getsockname(), timeout=5) as raw:
            with context.wrap_socket(raw, server_hostname="localhost") as secure:
                secure.sendall(b"fallback-ca")
                if secure.recv(64) != b"fallback-ca":
                    raise RuntimeError("TLS server returned the wrong payload")
    finally:
        listener.close()
        thread.join(timeout=10)
    if failures:
        raise RuntimeError("TLS server failed: " + "; ".join(failures))
    if thread.is_alive():
        raise RuntimeError("TLS server did not finish")

environment = os.environ
for name in ("SSL_CERT_FILE", "SSL_CERT_DIR", "PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE"):
    environment.pop(name, None)
missing_bundle = os.path.join(sys.prefix, "python-build-no-such-ca.pem")
ssl._PYTHON_BUILD_DEFAULT_CA_BUNDLE = missing_bundle
system_default_error = None
system_default_count = 0
try:
    system_default = ssl.create_default_context()
    system_default_count = system_default.cert_store_stats()["x509_ca"]
except (OSError, ssl.SSLError) as error:
    system_default_error = str(error)
finally:
    ssl._PYTHON_BUILD_DEFAULT_CA_BUNDLE = original_bundle
system_fallback_suppressed = (
    system_default_error is None and system_default_count > 0
)
empty_store_fallback_attempted = (
    system_default_count == 0
    and system_default_error is not None
    and missing_bundle in system_default_error
)
if not (system_fallback_suppressed or empty_store_fallback_attempted):
    raise RuntimeError(
        "default trust-store behavior was unexpected: "
        f"CA count={system_default_count}, error={system_default_error!r}"
    )
actual_default = ssl.create_default_context()
actual_default_ca_count = actual_default.cert_store_stats()["x509_ca"]
if actual_default_ca_count < 1:
    raise RuntimeError("create_default_context() returned an empty trust store")
if system_default_count and actual_default_ca_count != system_default_count:
    raise RuntimeError(
        "the populated system trust store changed: "
        f"before={system_default_count}, after={actual_default_ca_count}"
    )
ssl.SSLContext.set_default_verify_paths = lambda self: None
try:
    # First prove the real moved installation bundle loads without a system
    # trust store, then substitute the private fixture CA for a local TLS test.
    bundle_context = ssl.create_default_context()
    bundle_count = bundle_context.cert_store_stats()["x509_ca"]
    if bundle_count < 1:
        raise RuntimeError("moved bundle loaded no CA roots")
    ssl._PYTHON_BUILD_DEFAULT_CA_BUNDLE = certificate
    fallback_context = ssl.create_default_context()
    fallback_count = fallback_context.cert_store_stats()["x509_ca"]
    tls_roundtrip(fallback_context)
finally:
    ssl.SSLContext.set_default_verify_paths = original_default_paths
    ssl._PYTHON_BUILD_DEFAULT_CA_BUNDLE = original_bundle

with tempfile.TemporaryDirectory() as temporary:
    environment["SSL_CERT_FILE"] = certificate
    environment["SSL_CERT_DIR"] = os.path.join(temporary, "empty-ca-directory")
    explicit_context = ssl.create_default_context()
    explicit_count = explicit_context.cert_store_stats()["x509_ca"]
    if explicit_count != 1:
        raise RuntimeError(f"SSL_CERT_FILE should load only the fixture CA, got {explicit_count}")
    tls_roundtrip(explicit_context)

environment.pop("SSL_CERT_FILE", None)
environment.pop("SSL_CERT_DIR", None)
environment["PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE"] = "1"
ssl.SSLContext.set_default_verify_paths = lambda self: None
try:
    opted_out = ssl.create_default_context()
    opt_out_count = opted_out.cert_store_stats()["x509_ca"]
    if opt_out_count != 0:
        raise RuntimeError(f"opt-out loaded unexpected roots: {opt_out_count}")
finally:
    ssl.SSLContext.set_default_verify_paths = original_default_paths
    environment.pop("PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE", None)
print(json.dumps({
    "ok": True,
    "system_default_ca_count": system_default_count,
    "actual_default_ca_count": actual_default_ca_count,
    "system_fallback_suppressed_when_populated": system_fallback_suppressed,
    "empty_store_fallback_attempted": empty_store_fallback_attempted,
    "bundled_ca_count": bundle_count,
    "fallback_fixture_ca_count": fallback_count,
    "fallback_tls": True,
    "explicit_ssl_cert_file_ca_count": explicit_count,
    "explicit_ssl_cert_file_tls": True,
    "opt_out_ca_count": opt_out_count,
}))
'''
    test_environment = {
        name: value for name, value in environment.items()
        if name not in {
            "SSL_CERT_FILE", "SSL_CERT_DIR", "PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE",
            "PYTHONHOME", "PYTHONPATH",
        }
    }
    try:
        result = subprocess.run(
            [str(python), "-S", "-B", "-c", code, str(certificate), str(key)],
            cwd=install,
            env=test_environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return {"ok": False, "error": str(error)}
    try:
        data = json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {
            "ok": False,
            "error": f"fallback CA probe returned {result.returncode}: {result.stderr.strip()[-500:]}",
        }
    if result.returncode != 0:
        data["ok"] = False
        data["error"] = result.stderr.strip()[-1000:]
    return data


def _curses_tty_check(python: Path, install: Path, environment: dict[str, str]) -> dict:
    child, master = pty.fork()
    if child == 0:
        try:
            os.chdir(install)
            os.execve(
                str(python),
                [str(python), "-I", "-B", "-c", _CURSES_TTY_PROBE],
                environment,
            )
        except BaseException:
            os._exit(127)

    output = bytearray()
    deadline = time.monotonic() + 15
    status = None
    eof = False
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([master], [], [], 0.1)
            if ready:
                try:
                    chunk = os.read(master, 4096)
                except OSError:
                    chunk = b""
                if not chunk:
                    eof = True
                else:
                    output.extend(chunk)
            waited, child_status = os.waitpid(child, os.WNOHANG)
            if waited:
                status = child_status
            if status is not None and eof:
                break
        if status is None:
            try:
                os.kill(child, signal.SIGKILL)
            except ProcessLookupError:
                pass
            _, status = os.waitpid(child, 0)
            raise CompatibilityError("curses terminal probe timed out")
    finally:
        os.close(master)

    if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
        raise CompatibilityError(
            "curses terminal probe failed: " + output.decode(errors="replace")[-500:]
        )
    if b"PBS_TTY_OK" not in output:
        raise CompatibilityError("curses terminal probe did not finish cleanly")
    return {"status": "passed", "evidence": "curses initialized in a PTY"}


def run_standalone_compatibility(python: Path, install: Path, target: Target) -> dict:
    """Run applicable PBS distribution behavior checks against packaged bytes."""
    python = Path(python).resolve()
    install = Path(install).resolve()
    environment = _isolated_environment(target)
    source_lock = json.loads(
        (Path(__file__).resolve().parents[1] / "sources.lock.json").read_text()
    )
    locked_versions = {
        entry["name"]: entry["version"] for entry in source_lock["inputs"]
    }
    openssl_version = locked_versions["openssl"]
    major, minor, patch = (int(part) for part in openssl_version.split("."))
    if major < 3:
        raise CompatibilityError(
            f"unsupported pinned OpenSSL version for compatibility check: {openssl_version}"
        )
    environment["EXPECTED_OPENSSL_VERSION_INFO"] = f"{major},{minor},0,{patch},0"
    environment["EXPECTED_SQLITE_VERSION_INFO"] = locked_versions["sqlite"].replace(
        ".", ","
    )
    process = subprocess.run(
        [str(python), "-I", "-B", "-c", _RUNTIME_PROBE],
        cwd=install,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
    )
    try:
        report = json.loads(process.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise CompatibilityError(
            "could not read standalone compatibility results: "
            f"returncode={process.returncode}, "
            f"stdout={process.stdout[-1000:]!r}, stderr={process.stderr[-1000:]!r}"
        ) from error

    checks = report.get("checks")
    if not isinstance(checks, dict):
        raise CompatibilityError("standalone compatibility probe returned no checks")
    for name, function in (
        ("interpreter_getpath", lambda: _getpath_check(python, install, environment)),
        ("relocated_sysconfig", lambda: _relocated_sysconfig_check(python, install, environment)),
        ("fallback_ca", lambda: _fallback_ca_check(python, install, environment)),
        ("curses_tty", lambda: _curses_tty_check(python, install, environment)),
    ):
        try:
            result = function()
            result["status"] = _compatibility_status(result)
            checks[name] = result
        except (CompatibilityError, OSError, subprocess.SubprocessError) as error:
            checks[name] = {"status": "failed", "error": str(error)}

    report["checks"] = checks
    report["ok"] = process.returncode == 0 and not any(
        result.get("status") == "failed" for result in checks.values()
    )
    if process.stderr.strip():
        report["stderr"] = process.stderr.strip()[-2000:]
    return report
