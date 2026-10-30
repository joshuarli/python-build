from __future__ import annotations

import argparse
import json
import selectors
import socket
import ssl
import subprocess
import sys
import warnings
from pathlib import Path
from typing import Any

REFERENCE_BACKEND = "OpenSSL 3.5.7"
SERVER_CERT = "keycert3.pem"
CA_CERT = "pycacert.pem"
DH_PARAMS = "ffdh3072.pem"
HOSTNAME = "localhost"
TIMEOUT = 4.0

MODERN_TLS12_CIPHERS = {
    "ECDHE-ECDSA-AES128-GCM-SHA256",
    "ECDHE-RSA-AES128-GCM-SHA256",
    "ECDHE-ECDSA-AES256-GCM-SHA384",
    "ECDHE-RSA-AES256-GCM-SHA384",
    "ECDHE-ECDSA-CHACHA20-POLY1305",
    "ECDHE-RSA-CHACHA20-POLY1305",
}
MODERN_TLS13_CIPHERS = {
    "TLS_AES_128_GCM_SHA256",
    "TLS_AES_256_GCM_SHA384",
    "TLS_CHACHA20_POLY1305_SHA256",
}
MODERN_GROUPS = {
    "X25519MLKEM768",
    "x25519",
    "secp256r1",
    "secp384r1",
}
MODERN_SIGALGS = {
    "ecdsa_secp256r1_sha256",
    "ecdsa_secp384r1_sha384",
    "ed25519",
    "rsa_pss_rsae_sha512",
    "rsa_pss_rsae_sha384",
    "rsa_pss_rsae_sha256",
    "rsa_pkcs1_sha512",
    "rsa_pkcs1_sha384",
    "rsa_pkcs1_sha256",
}

POSITIVE_CASES = (
    {
        "name": "verified_tls12",
        "version": "TLSv1_2",
        "expected_version": "TLSv1.2",
        "allowed_ciphers": MODERN_TLS12_CIPHERS,
    },
    {
        "name": "verified_tls13",
        "version": "TLSv1_3",
        "expected_version": "TLSv1.3",
        "allowed_ciphers": MODERN_TLS13_CIPHERS,
    },
    {
        "name": "verified_tls13_hybrid",
        "version": "TLSv1_3",
        "expected_version": "TLSv1.3",
        "allowed_ciphers": MODERN_TLS13_CIPHERS,
        "groups": "X25519MLKEM768",
        "expected_group": "X25519MLKEM768",
    },
)

RETIRED_CASES = (
    {
        "name": "tls10",
        "version": "TLSv1",
        "expected_version": "TLSv1",
        "cipher": "ECDHE-RSA-AES128-SHA:@SECLEVEL=0",
        "expected_cipher": "ECDHE-RSA-AES128-SHA",
        "reference_required": True,
    },
    {
        "name": "tls11",
        "version": "TLSv1_1",
        "expected_version": "TLSv1.1",
        "cipher": "ECDHE-RSA-AES128-SHA:@SECLEVEL=0",
        "expected_cipher": "ECDHE-RSA-AES128-SHA",
        "reference_required": True,
    },
    {
        "name": "tls12_cbc",
        "version": "TLSv1_2",
        "expected_version": "TLSv1.2",
        "cipher": "ECDHE-RSA-AES128-SHA:@SECLEVEL=0",
        "expected_cipher": "ECDHE-RSA-AES128-SHA",
        "reference_required": True,
    },
    {
        "name": "tls12_static_rsa",
        "version": "TLSv1_2",
        "expected_version": "TLSv1.2",
        "cipher": "AES128-GCM-SHA256:@SECLEVEL=0",
        "expected_cipher": "AES128-GCM-SHA256",
        "reference_required": True,
    },
    {
        "name": "tls12_dhe",
        "version": "TLSv1_2",
        "expected_version": "TLSv1.2",
        "cipher": "DHE-RSA-AES128-GCM-SHA256:@SECLEVEL=0",
        "expected_cipher": "DHE-RSA-AES128-GCM-SHA256",
        "dh_params": DH_PARAMS,
        "reference_required": True,
    },
    {
        "name": "tls12_sha1_server_signature",
        "version": "TLSv1_2",
        "expected_version": "TLSv1.2",
        "cipher": "ECDHE-RSA-AES128-GCM-SHA256:@SECLEVEL=0",
        "expected_cipher": "ECDHE-RSA-AES128-GCM-SHA256",
        "server_sigalgs": "rsa_pkcs1_sha1",
        "client_sigalgs": "rsa_pkcs1_sha1",
        "expected_server_sigalg": "rsa_pkcs1_sha1",
        "reference_required": False,
    },
)


def _error_value(error: BaseException) -> dict[str, Any]:
    value: dict[str, Any] = {
        "type": type(error).__name__,
        "message": str(error),
    }
    for name in ("errno", "library", "reason", "verify_code", "verify_message"):
        item = getattr(error, name, None)
        if item is not None:
            value[name] = item
    return value


def _session_value(connection: Any) -> dict[str, Any]:
    cipher = connection.cipher()
    server_sigalg = getattr(connection, "server_sigalg", None)
    if callable(server_sigalg):
        server_sigalg = server_sigalg()
    return {
        "version": connection.version(),
        "cipher": cipher[0] if cipher else None,
        "server_sigalg": server_sigalg,
        "group": connection.group(),
    }


def _version_bounds(context: ssl.SSLContext, version: str) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        value = getattr(ssl.TLSVersion, version)
        context.minimum_version = value
        context.maximum_version = value


def _reference_server(config: dict[str, Any]) -> int:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            _version_bounds(context, config["version"])
            if config.get("cipher"):
                context.set_ciphers(config["cipher"])
            if config.get("groups"):
                context.set_groups(config["groups"])
            if config.get("server_sigalgs"):
                context.set_server_sigalgs(config["server_sigalgs"])
            if config.get("dh_params"):
                context.load_dh_params(config["dh_params"])
            context.load_cert_chain(config["certificate"])
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.settimeout(config["timeout"])
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
    except Exception as error:  # noqa: BLE001
        print(json.dumps({"setup_error": _error_value(error)}), flush=True)
        return 1

    print(
        json.dumps(
            {
                "ready": True,
                "backend": ssl.OPENSSL_VERSION,
                "python_version": list(sys.version_info[:3]),
                "port": listener.getsockname()[1],
            }
        ),
        flush=True,
    )
    try:
        raw, _ = listener.accept()
        raw.settimeout(config["timeout"])
        try:
            with context.wrap_socket(raw, server_side=True) as connection:
                result = {"accepted": True, **_session_value(connection)}
        except Exception as error:  # noqa: BLE001
            result = {"accepted": False, "error": _error_value(error)}
    except Exception as error:  # noqa: BLE001
        result = {"accepted": False, "error": _error_value(error)}
    finally:
        listener.close()
    print(json.dumps(result), flush=True)
    return 0


def _reference_client(config: dict[str, Any]) -> int:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            _version_bounds(context, config["version"])
            if config.get("cipher"):
                context.set_ciphers(config["cipher"])
            if config.get("client_sigalgs"):
                context.set_client_sigalgs(config["client_sigalgs"])
        raw = socket.create_connection(
            ("127.0.0.1", config["port"]), timeout=config["timeout"]
        )
        raw.settimeout(config["timeout"])
        try:
            with context.wrap_socket(raw, server_hostname=HOSTNAME) as connection:
                result = {"accepted": True, **_session_value(connection)}
        except Exception as error:  # noqa: BLE001
            result = {"accepted": False, "error": _error_value(error)}
    except Exception as error:  # noqa: BLE001
        result = {"accepted": False, "error": _error_value(error)}
    print(json.dumps(result), flush=True)
    return 0


def _worker_main() -> int | None:
    if len(sys.argv) < 2 or sys.argv[1] != "--worker":
        return None
    if len(sys.argv) != 4:
        print(json.dumps({"worker_error": "invalid worker arguments"}), flush=True)
        return 2
    role = sys.argv[2]
    config = json.loads(sys.argv[3])
    if role == "server":
        return _reference_server(config)
    if role == "client":
        return _reference_client(config)
    print(json.dumps({"worker_error": f"unknown worker role {role}"}), flush=True)
    return 2


def _read_line(process: subprocess.Popen[str], timeout: float) -> str:
    if process.stdout is None:
        raise RuntimeError("server worker stdout is unavailable")
    selector = selectors.DefaultSelector()
    try:
        selector.register(process.stdout, selectors.EVENT_READ)
        events = selector.select(timeout)
        if not events:
            raise TimeoutError("reference server worker timed out")
        line = process.stdout.readline()
        if not line:
            raise RuntimeError("reference server worker exited without a result")
        return line
    finally:
        selector.close()


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1.0)
    if process.stdout is not None:
        process.stdout.close()
    if process.stderr is not None:
        process.stderr.close()


def _reference_exchange(
    interpreter: Path,
    server_config: dict[str, Any],
    client_config: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    command = [
        str(interpreter),
        "-I",
        "-B",
        str(Path(__file__).resolve()),
        "--worker",
        "server",
        json.dumps(server_config),
    ]
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        ready = json.loads(_read_line(process, timeout))
        if not ready.get("ready"):
            process.wait(timeout=timeout)
            stderr = process.stderr.read() if process.stderr is not None else ""
            return {
                "server_ready": False,
                "server_setup": ready,
                "server_stderr": stderr,
            }
        if not ready["backend"].startswith(REFERENCE_BACKEND):
            return {
                "server_ready": False,
                "server_setup": {
                    "error": f"unexpected reference backend {ready['backend']}"
                },
            }
        if ready["python_version"] != [3, 15, 1]:
            return {
                "server_ready": False,
                "server_setup": {
                    "error": f"unexpected reference CPython version {ready['python_version']}"
                },
            }

        client_config = dict(client_config)
        client_config["port"] = ready["port"]
        client_config["timeout"] = timeout
        client_command = [
            str(interpreter),
            "-I",
            "-B",
            str(Path(__file__).resolve()),
            "--worker",
            "client",
            json.dumps(client_config),
        ]
        try:
            completed = subprocess.run(
                client_command,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout + 2.0,
                check=False,
            )
            client = json.loads(completed.stdout)
            if completed.returncode != 0:
                client["worker_exit"] = completed.returncode
                client["worker_stderr"] = completed.stderr
        except subprocess.TimeoutExpired as error:
            client = {
                "accepted": False,
                "error": {
                    "type": "TimeoutError",
                    "message": str(error),
                },
            }

        server = json.loads(_read_line(process, timeout + 2.0))
        process.wait(timeout=1.0)
        stderr = process.stderr.read() if process.stderr is not None else ""
        return {
            "server_ready": True,
            "backend": ready["backend"],
            "client": client,
            "server": server,
            "server_exit": process.returncode,
            "server_stderr": stderr,
        }
    finally:
        _stop_process(process)


def _candidate_context(cafile: Path, version: str | None = None) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    if hasattr(ssl, "VERIFY_X509_STRICT"):
        context.verify_flags |= ssl.VERIFY_X509_STRICT
    context.load_verify_locations(cafile=str(cafile))
    if version is not None:
        _version_bounds(context, version)
    return context


def _candidate_client(
    context: ssl.SSLContext, port: int, timeout: float
) -> dict[str, Any]:
    raw: socket.socket | None = None
    try:
        raw = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        raw.settimeout(timeout)
        with context.wrap_socket(
            raw,
            server_hostname=HOSTNAME,
            do_handshake_on_connect=False,
        ) as connection:
            try:
                connection.do_handshake()
            except Exception as error:  # noqa: BLE001
                return {
                    "accepted": False,
                    "phase": "handshake",
                    "error": _error_value(error),
                }
            return {
                "accepted": True,
                "phase": "handshake",
                **_session_value(connection),
                "peer_certificate": connection.getpeercert(),
                "verify_mode": int(context.verify_mode),
                "check_hostname": context.check_hostname,
                "verify_flags": int(context.verify_flags),
            }
    except Exception as error:  # noqa: BLE001
        return {
            "accepted": False,
            "phase": "connect_or_wrap",
            "error": _error_value(error),
        }
    finally:
        if raw is not None:
            raw.close()


def _candidate_exchange(
    context: ssl.SSLContext,
    reference: Path,
    server_config: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    server_command = [
        str(reference),
        "-I",
        "-B",
        str(Path(__file__).resolve()),
        "--worker",
        "server",
        json.dumps(server_config),
    ]
    process = subprocess.Popen(
        server_command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        ready = json.loads(_read_line(process, timeout))
        if not ready.get("ready"):
            process.wait(timeout=timeout)
            stderr = process.stderr.read() if process.stderr is not None else ""
            return {
                "server_ready": False,
                "server_setup": ready,
                "server_stderr": stderr,
            }
        if not ready["backend"].startswith(REFERENCE_BACKEND):
            return {
                "server_ready": False,
                "server_setup": {
                    "error": f"unexpected reference backend {ready['backend']}"
                },
            }
        if ready["python_version"] != [3, 15, 1]:
            return {
                "server_ready": False,
                "server_setup": {
                    "error": f"unexpected reference CPython version {ready['python_version']}"
                },
            }
        client = _candidate_client(context, ready["port"], timeout)
        server = json.loads(_read_line(process, timeout + 2.0))
        process.wait(timeout=1.0)
        stderr = process.stderr.read() if process.stderr is not None else ""
        return {
            "server_ready": True,
            "backend": ready["backend"],
            "client": client,
            "server": server,
            "server_exit": process.returncode,
            "server_stderr": stderr,
        }
    finally:
        _stop_process(process)


def _candidate_capabilities() -> dict[str, Any]:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    return {
        "backend": ssl.OPENSSL_VERSION,
        "python_version": list(sys.version_info[:3]),
        "version_info": list(ssl.OPENSSL_VERSION_INFO),
        "has_tls": {
            name: getattr(ssl, name)
            for name in ("HAS_TLSv1", "HAS_TLSv1_1", "HAS_TLSv1_2", "HAS_TLSv1_3")
        },
        "ciphers": [entry["name"] for entry in context.get_ciphers()],
        "groups": context.get_groups(),
        "sigalgs": ssl.get_sigalgs(),
    }


def _public_context_state(context: ssl.SSLContext) -> dict[str, Any]:
    return {
        "ciphers": [entry["name"] for entry in context.get_ciphers()],
        "groups": context.get_groups(),
        "sigalgs": ssl.get_sigalgs(),
        "minimum_version": int(context.minimum_version),
        "maximum_version": int(context.maximum_version),
        "verify_flags": int(context.verify_flags),
        "verify_mode": int(context.verify_mode),
        "check_hostname": context.check_hostname,
    }


def _check_advertised_capabilities(capabilities: dict[str, Any]) -> list[str]:
    failures = []
    if capabilities["python_version"] != [3, 15, 1]:
        failures.append("candidate is not the pinned CPython 3.15.1 runtime")
    if not capabilities["backend"].startswith("Rustls "):
        failures.append("candidate does not identify its Rustls backend truthfully")
    if capabilities["has_tls"] != {
        "HAS_TLSv1": False,
        "HAS_TLSv1_1": False,
        "HAS_TLSv1_2": True,
        "HAS_TLSv1_3": True,
    }:
        failures.append("TLS capability flags do not match the modern-only policy")
    if set(capabilities["ciphers"]) != MODERN_TLS12_CIPHERS | MODERN_TLS13_CIPHERS:
        failures.append("advertised cipher suites differ from the modern-only policy")
    if set(capabilities["groups"]) != MODERN_GROUPS:
        failures.append("advertised key-exchange groups differ from the modern-only policy")
    if set(capabilities["sigalgs"]) != MODERN_SIGALGS:
        failures.append("advertised signature algorithms differ from the modern-only policy")
    if any("sha1" in name.lower() for name in capabilities["sigalgs"]):
        failures.append("candidate advertises a SHA-1 handshake signature")
    return failures


def _check_unsupported_setters(
    context: ssl.SSLContext,
) -> list[dict[str, Any]]:
    checks = (
        (
            "tls12_cbc_cipher",
            lambda current: current.set_ciphers("ECDHE-RSA-AES128-SHA"),
        ),
        (
            "tls12_static_rsa_cipher",
            lambda current: current.set_ciphers("AES128-GCM-SHA256"),
        ),
        (
            "tls12_dhe_cipher",
            lambda current: current.set_ciphers("DHE-RSA-AES128-GCM-SHA256"),
        ),
        (
            "finite_field_group",
            lambda current: current.set_groups("ffdhe3072"),
        ),
        (
            "sha1_client_signature",
            lambda current: current.set_client_sigalgs("rsa_pkcs1_sha1"),
        ),
        (
            "sha1_server_signature",
            lambda current: current.set_server_sigalgs("rsa_pkcs1_sha1"),
        ),
    )
    results = []
    for name, setter in checks:
        before = _public_context_state(context)
        try:
            setter(context)
        except Exception as error:  # noqa: BLE001
            after = _public_context_state(context)
            results.append(
                {
                    "name": name,
                    "raised": type(error).__name__,
                    "message": str(error),
                    "state_unchanged": after == before,
                }
            )
        else:
            results.append(
                {
                    "name": name,
                    "raised": None,
                    "message": "setter unexpectedly accepted retired capability",
                    "state_unchanged": False,
                }
            )
    return results


def _server_config(case: dict[str, Any], certdata: Path, timeout: float) -> dict[str, Any]:
    return {
        "version": case["version"],
        "cipher": case.get("cipher"),
        "server_sigalgs": case.get("server_sigalgs"),
        "groups": case.get("groups"),
        "dh_params": str(certdata / case["dh_params"]) if case.get("dh_params") else None,
        "certificate": str(certdata / SERVER_CERT),
        "timeout": timeout,
    }


def _reference_client_config(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": case["version"],
        "cipher": case.get("cipher"),
        "client_sigalgs": case.get("client_sigalgs"),
    }


def _reference_offer(exchange: dict[str, Any], case: dict[str, Any]) -> tuple[bool, str]:
    if not exchange.get("server_ready"):
        return False, str(exchange.get("server_setup"))
    client = exchange["client"]
    server = exchange["server"]
    if not client.get("accepted"):
        return False, "reference client did not complete handshake: " + str(client.get("error"))
    if not server.get("accepted"):
        return False, "reference server did not complete handshake: " + str(server.get("error"))
    if client.get("version") != case["expected_version"]:
        return False, "reference selected unexpected protocol " + str(client.get("version"))
    if server.get("version") != case["expected_version"]:
        return False, "reference server reported unexpected protocol " + str(server.get("version"))
    if client.get("cipher") != case["expected_cipher"]:
        return False, "reference selected unexpected cipher " + str(client.get("cipher"))
    if server.get("cipher") != case["expected_cipher"]:
        return False, "reference server selected unexpected cipher " + str(server.get("cipher"))
    expected_sigalg = case.get("expected_server_sigalg")
    if expected_sigalg is not None and client.get("server_sigalg") != expected_sigalg:
            return False, "reference selected unexpected server signature " + str(
                client.get("server_sigalg")
            )
    return True, "reference negotiated the configured retired feature"


def _candidate_rejection(exchange: dict[str, Any]) -> tuple[bool, str]:
    if not exchange.get("server_ready"):
        return False, "candidate server setup failed: " + str(exchange.get("server_setup"))
    client = exchange["client"]
    server = exchange["server"]
    if client.get("accepted"):
        return False, "candidate negotiated a retired feature"
    client_error = client.get("error") or {}
    server_error = server.get("error") or {}
    client_type = client_error.get("type")
    if client_type in ("TimeoutError", "socket.timeout"):
        return False, "candidate timed out instead of rejecting the TLS policy"
    if client_type == "SSLCertVerificationError" or "verify_code" in client_error:
        return False, "candidate rejected the peer certificate rather than TLS policy"
    if client.get("phase") != "handshake":
        return False, "candidate failed before the TLS handshake: " + str(client_error)
    if client_type != "SSLError":
        return False, "candidate failure was not an SSL protocol error: " + str(client_error)
    if server.get("accepted"):
        return False, "reference server completed a handshake after candidate reported failure"
    if server_error.get("type") in ("TimeoutError", "socket.timeout"):
        return False, "reference server timed out instead of observing candidate rejection"
    if server_error.get("type") != "SSLError":
        return False, "reference server did not observe a TLS protocol error: " + str(server_error)
    return True, "candidate rejected the offered protocol, cipher, or signature during handshake"


def _check_positive(
    exchange: dict[str, Any], case: dict[str, Any]
) -> tuple[bool, str]:
    if not exchange.get("server_ready"):
        return False, "reference server setup failed: " + str(exchange.get("server_setup"))
    client = exchange["client"]
    server = exchange["server"]
    if not client.get("accepted"):
        return False, "verified candidate handshake failed: " + str(client.get("error"))
    if not server.get("accepted"):
        return False, "reference server handshake failed: " + str(server.get("error"))
    if client.get("version") != case["expected_version"]:
        return False, "candidate negotiated unexpected protocol " + str(client.get("version"))
    if client.get("cipher") not in case["allowed_ciphers"]:
        return False, "candidate negotiated an unadvertised cipher " + str(client.get("cipher"))
    if client.get("verify_mode") != int(ssl.CERT_REQUIRED):
        return False, "candidate client did not require certificate verification"
    if client.get("check_hostname") is not True:
        return False, "candidate client did not check the server hostname"
    if not client.get("verify_flags", 0) & int(getattr(ssl, "VERIFY_X509_STRICT", 0)):
        return False, "candidate client did not enable strict certificate verification"
    certificate = client.get("peer_certificate") or {}
    if ("DNS", HOSTNAME) not in certificate.get("subjectAltName", ()):
        return False, "candidate did not verify the expected localhost certificate"
    if server.get("version") != case["expected_version"]:
        return False, "reference server reported unexpected protocol " + str(server.get("version"))
    if server.get("cipher") != client.get("cipher"):
        return False, "candidate and reference server disagree on the negotiated cipher"
    if case.get("expected_group") and (
        client.get("group") != case["expected_group"]
        or server.get("group") != case["expected_group"]
    ):
            return False, "candidate and reference did not negotiate the required group"
    return True, "verified candidate handshake negotiated the expected modern protocol"


def _run_contract(reference: Path, certdata: Path, timeout: float) -> dict[str, Any]:
    capabilities = _candidate_capabilities()
    capability_failures = _check_advertised_capabilities(capabilities)
    cafile = certdata / CA_CERT
    context = _candidate_context(cafile, "TLSv1_2")
    setter_results = _check_unsupported_setters(context)
    setter_failures = [
        result
        for result in setter_results
        if result["raised"] != "SSLError" or not result["state_unchanged"]
    ]

    matrix: list[dict[str, Any]] = []
    failures = list(capability_failures)
    if setter_failures:
        failures.append("one or more unsupported setters failed to reject atomically")
    for case in POSITIVE_CASES:
        if case["name"] == "verified_tls12":
            candidate_context = context
        else:
            candidate_context = _candidate_context(cafile, case["version"])
        if case.get("groups"):
            candidate_context.set_groups(case["groups"])
        server = _server_config(case, certdata, timeout)
        exchange = _candidate_exchange(candidate_context, reference, server, timeout)
        passed, detail = _check_positive(exchange, case)
        matrix.append(
            {
                "name": case["name"],
                "kind": "positive_control",
                "reference_available": exchange.get("server_ready", False),
                "reference": {
                    "backend": exchange.get("backend"),
                    "server": exchange.get("server"),
                },
                "candidate": exchange.get("client"),
                "status": "passed" if passed else "failed",
                "detail": detail,
            }
        )
        if not passed:
            failures.append(case["name"] + ": " + detail)

    unavailable: list[str] = []
    for case in RETIRED_CASES:
        server = _server_config(case, certdata, timeout)
        reference_exchange = _reference_exchange(
            reference,
            server,
            _reference_client_config(case),
            timeout,
        )
        available, availability_detail = _reference_offer(reference_exchange, case)
        row: dict[str, Any] = {
            "name": case["name"],
            "kind": "retired_feature",
            "reference_available": available,
            "reference": reference_exchange,
            "candidate": None,
        }
        if not available:
            row["status"] = "reference_unavailable"
            row["detail"] = availability_detail
            unavailable.append(case["name"])
            if case["reference_required"]:
                failures.append(case["name"] + " reference unavailable: " + availability_detail)
            matrix.append(row)
            continue

        candidate_context = _candidate_context(cafile)
        candidate_exchange = _candidate_exchange(
            candidate_context, reference, server, timeout
        )
        rejected, rejection_detail = _candidate_rejection(candidate_exchange)
        row["candidate"] = candidate_exchange.get("client")
        row["candidate_server"] = candidate_exchange.get("server")
        row["status"] = "candidate_rejected" if rejected else "failed"
        row["detail"] = rejection_detail
        matrix.append(row)
        if not rejected:
            failures.append(case["name"] + ": " + rejection_detail)

    if failures:
        status = "failed"
        exit_code = 1
    elif unavailable:
        status = "incomplete"
        exit_code = 2
    else:
        status = "passed"
        exit_code = 0
    return {
        "status": status,
        "candidate_backend": capabilities["backend"],
        "reference_backend": REFERENCE_BACKEND,
        "candidate_capabilities": capabilities,
        "unsupported_setters": setter_results,
        "matrix": matrix,
        "unavailable_cases": unavailable,
        "failures": failures,
        "exit_code": exit_code,
    }


def main(argv: list[str] | None = None) -> int:
    worker_status = _worker_main()
    if worker_status is not None:
        return worker_status

    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--certdata", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=TIMEOUT)
    args = parser.parse_args(argv)
    reference = args.reference.resolve()
    certdata = args.certdata.resolve()
    if args.timeout <= 0 or args.timeout > 30:
        parser.error("--timeout must be greater than 0 and at most 30 seconds")
    if not reference.is_file() or not certdata.is_dir():
        parser.error("reference interpreter or certdata path does not exist")
    if not ssl.OPENSSL_VERSION.startswith("Rustls "):
        parser.error("run this contract with the isolated RTLS candidate interpreter")
    if reference.name != "python3.15":
        parser.error("reference must be the pinned CPython interpreter")
    if not (certdata / SERVER_CERT).is_file() or not (certdata / CA_CERT).is_file():
        parser.error("certdata must contain keycert3.pem and pycacert.pem")

    result = _run_contract(reference, certdata, args.timeout)
    print(json.dumps(result, indent=2, sort_keys=True))
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
