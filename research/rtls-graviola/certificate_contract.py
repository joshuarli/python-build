from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


REFERENCE_BACKEND_PREFIX = "OpenSSL 3.5.7"
REFERENCE_EXPECTATIONS = {
    "load_valid_chain": {"accepted": True},
    "load_malformed_trailing_pem": {"accepted": False},
    "load_malformed_middle_pem": {"accepted": False},
    "load_malformed_base64": {"accepted": False},
    "load_truncated_der": {"accepted": False},
    "load_surrounding_text": {"accepted": True},
    "load_mismatched_key": {"accepted": False},
    "load_encrypted_key_without_password": {"accepted": False},
    "load_encrypted_key_correct_password": {"accepted": True},
    "load_encrypted_key_wrong_password": {"accepted": False},
    "load_duplicate_critical_extension": {"accepted": True},
    "valid_path": {"accepted": True},
    "strict_missing_aki_default": {"accepted": False, "error.verify_code": 85},
    "strict_missing_aki_disabled": {"accepted": True},
    "partial_chain_enabled": {"accepted": True},
    "partial_chain_disabled": {"accepted": False},
    "trusted_first_disabled": {"accepted": True},
    "strict_basic_constraints_missing": {"accepted": False, "error.verify_code": 79},
    "strict_basic_constraints_missing_disabled": {"accepted": False, "error.verify_code": 79},
    "strict_basic_constraints_noncritical": {"accepted": False, "error.verify_code": 89},
    "strict_basic_constraints_noncritical_disabled": {"accepted": True},
    "strict_key_usage_missing": {"accepted": False, "error.verify_code": 81},
    "strict_key_usage_missing_disabled": {"accepted": True},
    "strict_key_usage_no_keycertsign": {"accepted": False, "error.verify_code": 79},
    "strict_key_usage_no_keycertsign_disabled": {"accepted": False, "error.verify_code": 79},
    "strict_subject_key_identifier_missing": {
        "accepted": False,
        "error.verify_code": 86,
    },
    "strict_subject_key_identifier_missing_disabled": {"accepted": True},
    "strict_authority_key_identifier_missing": {"accepted": False, "error.verify_code": 85},
    "strict_authority_key_identifier_missing_disabled": {"accepted": True},
    "strict_signature_sha1": {"accepted": False, "error.verify_code": 68},
    "strict_signature_sha1_disabled": {"accepted": False},
    "strict_pathlen_exceeded": {"accepted": False, "error.verify_code": 25},
    "strict_issuer_subject_mismatch": {"accepted": False},
    "issuer_name_root_exact_control": {"accepted": True},
    "issuer_name_root_case_equivalent": {"accepted": True},
    "issuer_name_root_space_equivalent": {"accepted": True},
    "issuer_name_root_string_type_equivalent": {"accepted": True},
    "issuer_name_intermediate_exact_control": {"accepted": True},
    "issuer_name_intermediate_case_equivalent": {"accepted": True},
    "issuer_name_intermediate_space_equivalent": {"accepted": True},
    "issuer_name_intermediate_string_type_equivalent": {"accepted": True},
    "issuer_name_different_same_key_rejected": {"accepted": False},
    "hostname_wrong_san": {"accepted": False},
    "hostname_cn_without_san": {"accepted": True},
    "hostname_wildcard_single_suffix": {"accepted": False},
    "hostname_wildcard_multi_suffix_control": {"accepted": True},
    "hostname_wildcard_idna_public_suffix": {"accepted": False},
    "name_constraints_allowed_cn": {"accepted": True},
    "name_constraints_blocked_cn": {"accepted": False},
    "name_constraints_blocked_cn_check_hostname_disabled": {"accepted": False},
    "name_constraints_blocked_cn_common_name_disabled": {
        "accepted": True,
        "hostname_policy.host_flags": 36,
    },
    "name_constraints_blocked_cn_common_name_disabled_hostname": {
        "accepted": False,
        "hostname_policy.host_flags": 36,
    },
    "name_constraints_san_dns_precedence_allowed": {"accepted": True},
    "name_constraints_san_dns_precedence_blocked": {"accepted": False},
    "strict_duplicate_critical_extension": {"accepted": False},
    "strict_duplicate_critical_extension_disabled": {"accepted": False},
    "critical_aia_on_trust_root": {"accepted": False},
    "ns_cert_type_client_on_server_leaf": {"accepted": False, "error.verify_code": 26},
    "unrelated_malformed_peer_certificate": {"accepted": True},
    "self_issued_not_self_signed_pathlen": {"accepted": True},
    "self_issued_canonical_name_pathlen": {"accepted": True},
    "cross_signed_trusted_first_enabled": {"accepted": True},
    "cross_signed_trusted_first_disabled": {"accepted": True},
    "trusted_intermediate_partial_chain_enabled": {"accepted": True},
    "trusted_intermediate_partial_chain_disabled": {"accepted": False},
    "failed_load_identity_atomicity": {
        "accepted": False,
        "error_type": "SSLError",
        "after_accepted": False,
        "identity_preserved": False,
    },
}

for anchor_kind in ("root", "partial"):
    for anchor_eku, expected in (("any", False), ("server", True), ("client", False)):
        REFERENCE_EXPECTATIONS[
            "eku_"
            + anchor_kind
            + "_"
            + anchor_eku
            + "_purpose_server_auth_leaf_server_"
            + {"any": "0", "server": "1", "client": "2"}[anchor_eku]
        ] = {"accepted": expected}
    REFERENCE_EXPECTATIONS[
        "eku_"
        + anchor_kind
        + "_server_purpose_server_auth_leaf_client_0"
    ] = {"accepted": False}
    for anchor_eku, expected in (("any", False), ("client", True), ("server", False)):
        REFERENCE_EXPECTATIONS[
            "eku_"
            + anchor_kind
            + "_"
            + anchor_eku
            + "_purpose_client_auth_leaf_client_"
            + {"any": "0", "client": "1", "server": "2"}[anchor_eku]
        ] = {"accepted": expected}
    REFERENCE_EXPECTATIONS[
        "eku_"
        + anchor_kind
        + "_client_purpose_client_auth_leaf_server_0"
    ] = {"accepted": False}


WORKER = r'''
import hashlib
import json
import os
import select
import socket
import ssl
import subprocess
import sys
import threading
from pathlib import Path


SERVER_CODE = r"""
import json
import socket
import ssl
import sys


def error_value(error):
    result = {"type": type(error).__name__, "message": str(error)}
    if isinstance(error, ssl.SSLCertVerificationError):
        result["verify_code"] = error.verify_code
    return result


def main():
    try:
        chainfile = sys.argv[1]
        ciphers = sys.argv[2] or None
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        if ciphers and hasattr(ssl, "OPENSSL_VERSION"):
            context.set_ciphers(ciphers)
        context.load_cert_chain(chainfile)
        listener = socket.socket()
        listener.settimeout(10)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        print(json.dumps({"port": listener.getsockname()[1]}), flush=True)
        raw, _ = listener.accept()
        raw.settimeout(10)
        try:
            with context.wrap_socket(raw, server_side=True):
                pass
            status = {"peer_error": None}
        except ssl.SSLError as error:
            status = {"peer_error": error_value(error)}
        finally:
            listener.close()
        print(json.dumps(status), flush=True)
        return 0
    except BaseException as error:
        print(json.dumps({"server_error": error_value(error)}), flush=True)
        return 1


raise SystemExit(main())
"""


def error_value(error):
    result = {"type": type(error).__name__, "message": str(error)}
    if isinstance(error, ssl.SSLCertVerificationError):
        result["verify_code"] = error.verify_code
    return result


def verify_flags(context):
    names = (
        "VERIFY_X509_STRICT",
        "VERIFY_X509_PARTIAL_CHAIN",
        "VERIFY_X509_TRUSTED_FIRST",
    )
    value = int(context.verify_flags)
    return {
        "value": value,
        "enabled": [name for name in names if value & int(getattr(ssl, name, 0))],
        "available": {name: getattr(ssl, name, None) is not None for name in names},
        "required": list(names),
    }


def load_context(certfile, keyfile=None, password=None, ciphers=None):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    if ciphers and hasattr(ssl, "OPENSSL_VERSION"):
        context.set_ciphers(ciphers)
    context.load_cert_chain(
        str(certfile), str(keyfile) if keyfile else None, password=password
    )
    return context


def client_context(cafile, changes, case):
    context = ssl.create_default_context(cafile=str(cafile))
    if "hostname_checks_common_name" in case:
        requested = case["hostname_checks_common_name"]
        context.hostname_checks_common_name = requested
        if getattr(context, "hostname_checks_common_name", None) != requested:
            raise RuntimeError("hostname_checks_common_name did not retain its assigned value")
    if "check_hostname" in case:
        context.check_hostname = case["check_hostname"]
    return set_verify_flags(context, changes)


def set_verify_flags(context, changes):
    flags = int(context.verify_flags)
    for name, enabled in changes.items():
        flag = getattr(ssl, name, None)
        if flag is None:
            raise RuntimeError("required verification flag is unavailable: " + name)
        if enabled:
            flags |= int(flag)
        else:
            flags &= ~int(flag)
    context.verify_flags = flags
    return context


def exchange(server_context, client_context, hostname, allow_handshake_error=False):
    listener = socket.socket()
    listener.settimeout(5)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    server_errors = []

    def serve():
        try:
            raw, _ = listener.accept()
            raw.settimeout(5)
            with server_context.wrap_socket(raw, server_side=True):
                pass
        except BaseException as error:
            server_errors.append(error)
        finally:
            listener.close()

    thread = threading.Thread(target=serve)
    thread.start()
    outcome = None
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
            raw.settimeout(5)
            with client_context.wrap_socket(raw, server_hostname=hostname) as peer:
                certificate = peer.getpeercert(binary_form=True)
                outcome = {
                    "accepted": True,
                    "peer_sha256": hashlib.sha256(certificate).hexdigest(),
                    "error": None,
                    "phase": "handshake",
                }
    except ssl.SSLCertVerificationError as error:
        outcome = {
            "accepted": False,
            "peer_sha256": None,
            "error": error_value(error),
            "phase": "handshake",
        }
    except ssl.SSLError as error:
        if not allow_handshake_error:
            raise
        outcome = {
            "accepted": False,
            "peer_sha256": None,
            "error": error_value(error),
            "phase": "handshake",
        }
    finally:
        thread.join(6)
        if thread.is_alive():
            raise TimeoutError("TLS server did not finish")
    unexpected_server_errors = [
        error
        for error in server_errors
        if not isinstance(error, (ssl.SSLError, OSError)) or isinstance(error, TimeoutError)
    ]
    if unexpected_server_errors:
        raise RuntimeError("TLS server thread failed: " + str(unexpected_server_errors[0]))
    if outcome["accepted"] and server_errors:
        raise RuntimeError("TLS server failed after a successful client handshake")
    outcome["server_errors"] = [error_value(error) for error in server_errors]
    return outcome


def run_load_case(case):
    try:
        load_context(
            case["certfile"],
            case.get("keyfile"),
            case.get("password"),
        )
        return {"accepted": True, "error": None, "verify_flags": None}
    except ssl.SSLError as error:
        return {
            "accepted": False,
            "error": error_value(error),
            "verify_flags": None,
        }


def run_path_case(case):
    if case.get("purpose") == "CLIENT_AUTH":
        return run_client_auth_case(case)
    try:
        client = client_context(case["trustfile"], case.get("flags", {}), case)
        flags = verify_flags(client)
        hostname_policy = {
            "check_hostname": client.check_hostname,
            "hostname_checks_common_name": getattr(
                client, "hostname_checks_common_name", None
            ),
            "host_flags": getattr(client, "_host_flags", None),
        }
    except BaseException as error:
        return {
            "accepted": None,
            "peer_sha256": None,
            "error": None,
            "phase": "client_context_setup",
            "harness_error": error_value(error),
            "verify_flags": None,
        }
    try:
        result = exchange_reference_server(
            manifest_reference_interpreter,
            case["chainfile"],
            case.get("server_ciphers"),
            client,
            case.get("hostname", "localhost"),
        )
        result["verify_flags"] = flags
        result["hostname_policy"] = hostname_policy
        return result
    except BaseException as error:
        return {
            "accepted": None,
            "peer_sha256": None,
            "error": None,
            "phase": "handshake_execution",
            "harness_error": error_value(error),
            "verify_flags": None,
            "hostname_policy": None,
        }


def client_auth_exchange(server_context, client_context):
    listener = socket.socket()
    listener.settimeout(5)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    server_errors = []

    def serve():
        try:
            raw, _ = listener.accept()
            raw.settimeout(5)
            with server_context.wrap_socket(raw, server_side=True):
                pass
        except BaseException as error:
            server_errors.append(error)
        finally:
            listener.close()

    thread = threading.Thread(target=serve)
    thread.start()
    client_error = None
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
            raw.settimeout(5)
            with client_context.wrap_socket(raw, server_hostname="localhost"):
                pass
    except ssl.SSLError as error:
        client_error = error
    finally:
        thread.join(6)
        if thread.is_alive():
            raise TimeoutError("mutual TLS server did not finish")
    verification_errors = [
        error for error in server_errors if isinstance(error, ssl.SSLCertVerificationError)
    ]
    if verification_errors:
        return {
            "accepted": False,
            "peer_sha256": None,
            "error": error_value(verification_errors[0]),
            "phase": "handshake",
            "server_errors": [error_value(error) for error in server_errors],
        }
    if server_errors:
        raise RuntimeError("mutual TLS server thread failed: " + str(server_errors[0]))
    if client_error is not None:
        raise RuntimeError("mutual TLS client handshake failed: " + str(client_error))
    return {
        "accepted": True,
        "peer_sha256": None,
        "error": None,
        "phase": "handshake",
        "server_errors": [],
    }


def run_client_auth_case(case):
    try:
        server = ssl.create_default_context(
            purpose=ssl.Purpose.CLIENT_AUTH, cafile=str(case["trustfile"])
        )
        server.verify_mode = ssl.CERT_REQUIRED
        server = set_verify_flags(server, case.get("flags", {}))
        server.load_cert_chain(case["server_chainfile"])
        client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        client.check_hostname = False
        client.verify_mode = ssl.CERT_NONE
        client.load_cert_chain(case["chainfile"])
        flags = verify_flags(server)
    except BaseException as error:
        return {
            "accepted": None,
            "peer_sha256": None,
            "error": None,
            "phase": "client_auth_setup",
            "harness_error": error_value(error),
            "verify_flags": None,
            "hostname_policy": None,
        }
    try:
        result = client_auth_exchange(server, client)
        result["verify_flags"] = flags
        result["hostname_policy"] = {"verifier": "server", "purpose": "CLIENT_AUTH"}
        return result
    except BaseException as error:
        return {
            "accepted": None,
            "peer_sha256": None,
            "error": None,
            "phase": "client_auth_handshake_execution",
            "harness_error": error_value(error),
            "verify_flags": None,
            "hostname_policy": None,
        }


def run_atomic_case(case):
    try:
        server = load_context(case["baseline_chain"])
        before_client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        before_client.check_hostname = False
        before_client.verify_mode = ssl.CERT_NONE
        before = exchange(server, before_client, "localhost")
        if not before["accepted"]:
            raise RuntimeError("baseline identity could not complete a TLS handshake")
    except BaseException as error:
        return {
            "accepted": None,
            "error": None,
            "phase": "baseline_setup",
            "harness_error": error_value(error),
            "before": None,
            "after": None,
            "identity_preserved": False,
        }
    try:
        server.load_cert_chain(case["replacement_cert"], case["mismatched_key"])
        failure = None
    except ssl.SSLError as error:
        failure = error_value(error)
    except BaseException as error:
        return {
            "accepted": None,
            "error": None,
            "phase": "replacement_load",
            "harness_error": error_value(error),
            "before": before,
            "after": None,
            "identity_preserved": False,
        }
    after_client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    after_client.check_hostname = False
    after_client.verify_mode = ssl.CERT_NONE
    try:
        after = exchange(server, after_client, "localhost", allow_handshake_error=True)
    except BaseException as error:
        return {
            "accepted": None,
            "error": failure,
            "phase": "post_failure_handshake",
            "harness_error": error_value(error),
            "before": before,
            "after": None,
            "identity_preserved": False,
        }
    return {
        "accepted": failure is None,
        "error": failure,
        "phase": "replacement_load",
        "before": before,
        "after": after,
        "identity_preserved": (
            before["accepted"]
            and after["accepted"]
            and before["peer_sha256"] == after["peer_sha256"]
        ),
    }


def exchange_reference_server(interpreter, chainfile, ciphers, context, hostname):
    command = [
        interpreter,
        "-I",
        "-B",
        "-c",
        SERVER_CODE,
        str(chainfile),
        ciphers or "",
    ]
    server = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=os.environ.copy(),
    )
    readable, _, _ = select.select([server.stdout], [], [], 15)
    if not readable:
        server.kill()
        _, stderr = server.communicate()
        raise TimeoutError("reference TLS server did not become ready: " + stderr.strip())
    ready_line = server.stdout.readline()
    if not ready_line:
        _, stderr = server.communicate(timeout=15)
        raise RuntimeError("reference TLS server failed before listening: " + stderr.strip())
    ready = json.loads(ready_line)
    if "port" not in ready:
        _, stderr = server.communicate(timeout=15)
        raise RuntimeError(
            "reference TLS server setup failed: "
            + str(ready.get("server_error"))
            + " "
            + stderr.strip()
        )
    outcome = None
    try:
        with socket.create_connection(("127.0.0.1", ready["port"]), timeout=5) as raw:
            raw.settimeout(5)
            with context.wrap_socket(raw, server_hostname=hostname) as peer:
                certificate = peer.getpeercert(binary_form=True)
                outcome = {
                    "accepted": True,
                    "peer_sha256": hashlib.sha256(certificate).hexdigest(),
                    "error": None,
                    "phase": "handshake",
                }
    except ssl.SSLCertVerificationError as error:
        outcome = {
            "accepted": False,
            "peer_sha256": None,
            "error": {
                **error_value(error),
                "verify_code": getattr(error, "verify_code", None),
            },
            "phase": "handshake",
        }
    finally:
        try:
            stdout, stderr = server.communicate(timeout=12)
        except subprocess.TimeoutExpired:
            server.kill()
            server.communicate()
            raise TimeoutError("reference TLS server did not finish")
    if server.returncode != 0:
        raise RuntimeError("reference TLS server failed: " + stderr.strip())
    status_lines = [line for line in stdout.splitlines() if line.strip()]
    status = json.loads(status_lines[-1]) if status_lines else {}
    if outcome["accepted"] and status.get("peer_error"):
        raise RuntimeError("reference TLS server failed after an accepted handshake")
    if not outcome["accepted"] and not status.get("peer_error"):
        raise RuntimeError("reference TLS server did not observe the rejected handshake")
    outcome["server_error"] = status.get("peer_error")
    return outcome


def main():
    manifest = json.loads(Path(sys.argv[1]).read_text())
    initial = ssl.create_default_context()
    results = {
        "interpreter": sys.version.split()[0],
        "executable": str(Path(sys.executable).resolve()),
        "backend": getattr(ssl, "OPENSSL_VERSION", getattr(ssl, "__version__", "unknown")),
        "default_verify_flags": verify_flags(initial),
        "path_case_names": [case["name"] for case in manifest["path_cases"]],
        "cases": {},
    }
    global manifest_reference_interpreter
    manifest_reference_interpreter = manifest["reference_interpreter"]
    for case in manifest["load_cases"]:
        results["cases"][case["name"]] = run_load_case(case)
    for case in manifest["path_cases"]:
        results["cases"][case["name"]] = run_path_case(case)
    results["cases"]["failed_load_identity_atomicity"] = run_atomic_case(
        manifest["atomic_case"]
    )
    print(json.dumps(results, sort_keys=True))


main()
'''


def cert_blocks(data: bytes) -> list[bytes]:
    return re.findall(
        rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", data, re.S
    )


def private_key(data: bytes) -> bytes:
    markers = (
        b"-----BEGIN PRIVATE KEY-----",
        b"-----BEGIN RSA PRIVATE KEY-----",
        b"-----BEGIN ENCRYPTED PRIVATE KEY-----",
        b"-----BEGIN EC PRIVATE KEY-----",
    )
    positions = [(data.find(marker), marker) for marker in markers]
    positions = [(position, marker) for position, marker in positions if position >= 0]
    if not positions:
        raise ValueError("certificate fixture contains no private key")
    start, marker = min(positions)
    end_marker = marker.replace(b"BEGIN", b"END")
    end = data.find(end_marker, start)
    if end < 0:
        raise ValueError("private key PEM block is incomplete")
    end += len(end_marker)
    return data[start:end] + b"\n"


def write_fixture(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


def der_length(size: int) -> bytes:
    if size < 128:
        return bytes((size,))
    encoded = size.to_bytes((size.bit_length() + 7) // 8, "big")
    return bytes((0x80 | len(encoded),)) + encoded


def der_value(tag: int, contents: bytes) -> bytes:
    return bytes((tag,)) + der_length(len(contents)) + contents


def der_item(data: bytes, offset: int = 0) -> tuple[int, int, int, int]:
    tag = data[offset]
    length = data[offset + 1]
    start = offset + 2
    if length & 0x80:
        count = length & 0x7f
        length = int.from_bytes(data[start : start + count], "big")
        start += count
    end = start + length
    return tag, offset, start, end


def der_children(data: bytes) -> list[bytes]:
    _, _, offset, end = der_item(data)
    values = []
    while offset < end:
        _, start, _, item_end = der_item(data, offset)
        values.append(data[start:item_end])
        offset = item_end
    if offset != end:
        raise ValueError("certificate DER has an invalid length")
    return values


def pem_der(data: bytes) -> bytes:
    match = re.search(
        rb"-----BEGIN CERTIFICATE-----\s*(.*?)\s*-----END CERTIFICATE-----",
        data,
        re.S,
    )
    if match is None:
        raise ValueError("certificate fixture contains no PEM certificate")
    return base64.b64decode(re.sub(rb"\s+", b"", match.group(1)))


COMMON_NAME_OID = b"\x06\x03\x55\x04\x03"
ORGANIZATION_NAME_OID = b"\x06\x03\x55\x04\x0a"
SUBJECT_KEY_IDENTIFIER_EXTENSION_OID = b"\x06\x03\x55\x1d\x0e"
AUTHORITY_KEY_IDENTIFIER_EXTENSION_OID = b"\x06\x03\x55\x1d\x23"


def name_variant(name: bytes, oid: bytes, variant: str) -> bytes:
    rdns = []
    found = False
    for rdn in der_children(name):
        attributes = []
        for attribute in der_children(rdn):
            fields = der_children(attribute)
            if fields[0] != oid:
                attributes.append(attribute)
                continue
            if found or len(fields) != 2:
                raise ValueError("distinguished name attribute is not unique")
            found = True
            value_tag, _, value_offset, value_end = der_item(fields[1])
            value = fields[1][value_offset:value_end]
            if variant == "case":
                value = value.swapcase()
            elif variant == "spaces":
                value = (
                    value.replace(b" ", b"  ", 1)
                    if b" " in value
                    else b" " + value + b" "
                )
            elif variant == "string_type":
                if value_tag == 0x0c:
                    value_tag = 0x13
                elif value_tag == 0x13:
                    value_tag = 0x0c
                else:
                    raise ValueError(
                        "distinguished name string type is not UTF8String or PrintableString"
                    )
            elif variant == "different":
                value = b"unrecognized-issuer"
            else:
                raise ValueError(f"unknown distinguished name variant {variant!r}")
            attributes.append(der_value(0x30, fields[0] + der_value(value_tag, value)))
        rdns.append(der_value(0x31, b"".join(attributes)))
    if not found:
        raise ValueError("distinguished name attribute is missing")
    return der_value(0x30, b"".join(rdns))


def certificate_fields(certificate: bytes) -> tuple[list[bytes], bytes, bytes]:
    outer = der_children(certificate)
    if len(outer) != 3:
        raise ValueError("certificate DER does not have three outer fields")
    tbs_fields = der_children(outer[0])
    version_offset = 1 if tbs_fields[0][0] == 0xa0 else 0
    subject_offset = version_offset + 4
    issuer_offset = version_offset + 2
    return tbs_fields, tbs_fields[issuer_offset], tbs_fields[subject_offset]


def resign_certificate(
    certificate: bytes,
    fields: list[bytes],
    key: Path,
    directory: Path,
    openssl: str,
) -> bytes:
    outer = der_children(certificate)
    tbs = der_value(0x30, b"".join(fields))
    tbs_path = directory / "resign-tbs.der"
    signature_path = directory / "resign-signature.bin"
    tbs_path.write_bytes(tbs)
    run_openssl(
        openssl,
        directory,
        ["dgst", "-sha256", "-sign", str(key), "-out", str(signature_path), str(tbs_path)],
    )
    signature = der_value(0x03, b"\x00" + signature_path.read_bytes())
    return der_value(0x30, tbs + outer[1] + signature)


def remove_certificate_extension(
    certificate: bytes,
    oid: bytes,
    key: Path,
    directory: Path,
    openssl: str,
) -> bytes:
    der = pem_der(certificate)
    fields, _, _ = certificate_fields(der)
    extensions_index = next(
        (index for index, field in enumerate(fields) if field[0] == 0xa3), None
    )
    if extensions_index is None:
        return certificate
    explicit_extensions = der_children(fields[extensions_index])
    if len(explicit_extensions) != 1:
        raise ValueError("certificate extensions field is invalid")
    extensions = der_children(explicit_extensions[0])
    retained = [
        extension
        for extension in extensions
        if der_children(extension)[0] != oid
    ]
    if len(retained) == len(extensions):
        return certificate
    if len(retained) != len(extensions) - 1:
        raise ValueError("certificate has duplicate target extensions")
    fields[extensions_index] = der_value(0xa3, der_value(0x30, b"".join(retained)))
    revised = resign_certificate(der, fields, key, directory, openssl)
    revised_extensions = der_children(fields[extensions_index])
    if any(
        der_children(extension)[0] == oid
        for extension in der_children(revised_extensions[0])
    ):
        raise ValueError("certificate target extension remains after removal")
    return certificate_pem(revised)


def resigned_issuer_certificate(
    certificate: bytes,
    issuer: bytes,
    key: Path,
    directory: Path,
    openssl: str,
) -> bytes:
    der = pem_der(certificate)
    fields, _, _ = certificate_fields(der)
    issuer_offset = (1 if fields[0][0] == 0xa0 else 0) + 2
    fields[issuer_offset] = issuer
    return certificate_pem(resign_certificate(der, fields, key, directory, openssl))


def certificate_pem(certificate: bytes) -> bytes:
    encoded = base64.b64encode(certificate)
    rows = [encoded[offset : offset + 64] for offset in range(0, len(encoded), 64)]
    return b"-----BEGIN CERTIFICATE-----\n" + b"\n".join(rows) + b"\n-----END CERTIFICATE-----\n"


def run_openssl(openssl: str, directory: Path, arguments: list[str]) -> None:
    environment = os.environ.copy()
    environment["TMPDIR"] = str(directory)
    result = subprocess.run(
        [openssl] + arguments,
        cwd=str(directory),
        env=environment,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "openssl command failed: "
            + " ".join([openssl] + arguments)
            + "\n"
            + result.stderr.strip()
        )


def ca_state(directory: Path, certificate: Path, key: Path, name: str) -> dict[str, Path]:
    state = directory / ("ca-" + name)
    newcerts = state / "newcerts"
    newcerts.mkdir(parents=True)
    (state / "index.txt").write_text("")
    (state / "index.txt.attr").write_text("unique_subject = no\n")
    (state / "serial").write_text("01\n")
    config = state / "openssl.cnf"
    config.write_text(
        "\n".join(
            (
                "[ca]",
                "default_ca = CA_default",
                "[CA_default]",
                f'dir = "{state}"',
                "database = $dir/index.txt",
                "new_certs_dir = $dir/newcerts",
                f'certificate = "{certificate}"',
                f'private_key = "{key}"',
                "serial = $dir/serial",
                "default_md = sha256",
                "default_days = 3650",
                "default_crl_days = 3650",
                "policy = policy_anything",
                "unique_subject = no",
                "copy_extensions = none",
                "[policy_anything]",
                "commonName = supplied",
                "countryName = optional",
                "stateOrProvinceName = optional",
                "localityName = optional",
                "organizationName = optional",
                "organizationalUnitName = optional",
                "emailAddress = optional",
                "",
            )
        )
    )
    return {"directory": state, "config": config, "certificate": certificate, "key": key}


def ca_extensions(state: dict[str, Path], name: str, values: list[str]) -> None:
    with state["config"].open("a") as config:
        config.write("[" + name + "]\n")
        config.write("\n".join(values) + "\n\n")


def make_key_request(
    openssl: str, directory: Path, name: str, subject: str
) -> tuple[Path, Path]:
    key = directory / (name + ".key")
    request = directory / (name + ".csr")
    run_openssl(
        openssl,
        directory,
        [
            "req",
            "-new",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(request),
            "-subj",
            subject,
        ],
    )
    return key, request


def issue_certificate(
    openssl: str,
    state: dict[str, Path],
    request: Path,
    destination: Path,
    section: str,
    extensions: list[str],
    digest: str = "sha256",
) -> Path:
    ca_extensions(state, section, extensions)
    run_openssl(
        openssl,
        state["directory"],
        [
            "ca",
            "-config",
            str(state["config"]),
            "-in",
            str(request),
            "-out",
            str(destination),
            "-extensions",
            section,
            "-md",
            digest,
            "-batch",
            "-notext",
        ],
    )
    return destination


def make_root_b(openssl: str, directory: Path) -> tuple[Path, Path]:
    config = directory / "root-b-req.cnf"
    config.write_text(
        "\n".join(
            (
                "[req]",
                "prompt = no",
                "distinguished_name = dn",
                "x509_extensions = ca_ext",
                "[dn]",
                "CN = RTLS-Root-B",
                "[ca_ext]",
                "basicConstraints = critical,CA:true,pathlen:5",
                "keyUsage = critical,keyCertSign,cRLSign",
                "subjectKeyIdentifier = hash",
                "authorityKeyIdentifier = keyid:always,issuer",
                "",
            )
        )
    )
    key = directory / "root-b.key"
    certificate = directory / "root-b.pem"
    run_openssl(
        openssl,
        directory,
        [
            "req",
            "-x509",
            "-new",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(certificate),
            "-days",
            "3650",
            "-config",
            str(config),
        ],
    )
    return certificate, key


def make_policy_root(
    openssl: str, directory: Path, name: str, extensions: list[str]
) -> tuple[Path, Path]:
    config = directory / (name + "-req.cnf")
    config.write_text(
        "\n".join(
            (
                "[req]",
                "prompt = no",
                "distinguished_name = dn",
                "x509_extensions = ca_ext",
                "[dn]",
                "CN = RTLS-" + name,
                "[ca_ext]",
                *extensions,
                "",
            )
        )
    )
    key = directory / (name + ".key")
    certificate = directory / (name + ".pem")
    run_openssl(
        openssl,
        directory,
        [
            "req",
            "-x509",
            "-new",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(certificate),
            "-days",
            "3650",
            "-config",
            str(config),
        ],
    )
    return certificate, key


def make_eku_policy_cases(
    certdata: Path,
    directory: Path,
    openssl: str,
    normal_intermediate: list[str],
) -> list[dict[str, object]]:
    root_a = certdata / "pycacert.pem"
    root_a_key = certdata / "pycakey.pem"
    root_state = ca_state(directory, root_a, root_a_key, "eku-partial-root")

    leaf_requests = {}
    for leaf_eku in ("server", "client"):
        key, request = make_key_request(
            openssl, directory, "eku-leaf-" + leaf_eku, "/CN=localhost"
        )
        leaf_requests[leaf_eku] = (key, request)

    def leaf_extensions(eku):
        values = [
            "basicConstraints = critical,CA:false",
            "keyUsage = critical,digitalSignature,keyEncipherment",
            "extendedKeyUsage = " + ("serverAuth" if eku == "server" else "clientAuth"),
            "subjectKeyIdentifier = hash",
            "authorityKeyIdentifier = keyid,issuer",
        ]
        if eku == "server":
            values.append("subjectAltName = DNS:localhost")
        return values

    def root_anchor(name, eku):
        config = directory / ("eku-root-" + name + ".cnf")
        config.write_text(
            "\n".join(
                (
                    "[req]",
                    "prompt = no",
                    "distinguished_name = dn",
                    "x509_extensions = ca_ext",
                    "[dn]",
                    "CN = RTLS-EKU-Root-" + name,
                    "[ca_ext]",
                    "basicConstraints = critical,CA:true,pathlen:5",
                    "keyUsage = critical,keyCertSign,cRLSign",
                    "subjectKeyIdentifier = hash",
                    "authorityKeyIdentifier = keyid:always,issuer",
                    "extendedKeyUsage = critical," + eku,
                    "",
                )
            )
        )
        key = directory / ("eku-root-" + name + ".key")
        certificate = directory / ("eku-root-" + name + ".pem")
        run_openssl(
            openssl,
            directory,
            [
                "req",
                "-x509",
                "-new",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(key),
                "-out",
                str(certificate),
                "-days",
                "3650",
                "-config",
                str(config),
            ],
        )
        return certificate, key

    anchors = {}
    for anchor_eku, eku_text in (
        ("any", "anyExtendedKeyUsage"),
        ("server", "serverAuth"),
        ("client", "clientAuth"),
    ):
        root_certificate, root_key = root_anchor(anchor_eku, eku_text)
        root_ca = ca_state(
            directory, root_certificate, root_key, "eku-root-" + anchor_eku
        )
        anchors[("root", anchor_eku)] = (root_certificate, root_key, root_ca)

        partial_key, partial_request = make_key_request(
            openssl,
            directory,
            "eku-partial-" + anchor_eku,
            "/CN=RTLS-EKU-Partial-" + anchor_eku,
        )
        partial_certificate = issue_certificate(
            openssl,
            root_state,
            partial_request,
            directory / ("eku-partial-" + anchor_eku + ".pem"),
            "eku_partial_" + anchor_eku,
            normal_intermediate
            + ["extendedKeyUsage = critical," + eku_text],
        )
        partial_ca = ca_state(
            directory,
            partial_certificate,
            partial_key,
            "eku-partial-ca-" + anchor_eku,
        )
        anchors[("partial", anchor_eku)] = (
            partial_certificate,
            partial_key,
            partial_ca,
        )

    cases = []
    scenario_rows = (
        ("SERVER_AUTH", "server", ("any", "server", "client")),
        ("SERVER_AUTH", "client", ("server",)),
        ("CLIENT_AUTH", "client", ("any", "client", "server")),
        ("CLIENT_AUTH", "server", ("client",)),
    )
    for anchor_kind in ("root", "partial"):
        for purpose, leaf_eku, anchor_ekus in scenario_rows:
            for index, anchor_eku in enumerate(anchor_ekus):
                certificate, key, signing_ca = anchors[(anchor_kind, anchor_eku)]
                _, request = leaf_requests[leaf_eku]
                leaf = issue_certificate(
                    openssl,
                    signing_ca,
                    request,
                    directory
                    / (
                        "eku-leaf-"
                        + anchor_kind
                        + "-"
                        + anchor_eku
                        + "-"
                        + purpose.lower()
                        + "-"
                        + leaf_eku
                        + "-"
                        + str(index)
                        + ".pem"
                    ),
                    "eku_leaf_"
                    + anchor_kind
                    + "_"
                    + anchor_eku
                    + "_"
                    + purpose.lower()
                    + "_"
                    + leaf_eku
                    + "_"
                    + str(index),
                    leaf_extensions(leaf_eku),
                )
                chainfile = directory / (
                    "eku-chain-"
                    + anchor_kind
                    + "-"
                    + anchor_eku
                    + "-"
                    + purpose.lower()
                    + "-"
                    + leaf_eku
                    + "-"
                    + str(index)
                    + ".pem"
                )
                chainfile.write_bytes(
                    leaf.read_bytes()
                    + (certificate.read_bytes() if anchor_kind == "partial" else b"")
                    + leaf_requests[leaf_eku][0].read_bytes()
                )
                case = {
                    "name": "eku_"
                    + anchor_kind
                    + "_"
                    + anchor_eku
                    + "_purpose_"
                    + purpose.lower()
                    + "_leaf_"
                    + leaf_eku
                    + "_"
                    + str(index),
                    "chainfile": str(chainfile),
                    "trustfile": str(certificate),
                    "purpose": purpose,
                }
                if purpose == "CLIENT_AUTH":
                    case["server_chainfile"] = str(certdata / "keycert3.pem")
                    case["flags"] = {
                        "VERIFY_X509_STRICT": True,
                        "VERIFY_X509_PARTIAL_CHAIN": True,
                        "VERIFY_X509_TRUSTED_FIRST": True,
                    }
                cases.append(case)
    return cases


def make_policy_fixtures(
    certdata: Path, directory: Path, openssl: str
) -> tuple[list[dict[str, object]], dict[str, str]]:
    root_a = certdata / "pycacert.pem"
    root_a_key = certdata / "pycakey.pem"
    root_state = ca_state(directory, root_a, root_a_key, "root-a")
    intermediate_key, intermediate_request = make_key_request(
        openssl, directory, "intermediate", "/CN=RTLS-Intermediate"
    )
    normal_intermediate = [
        "basicConstraints = critical,CA:true,pathlen:4",
        "keyUsage = critical,digitalSignature,keyCertSign,cRLSign",
        "subjectKeyIdentifier = hash",
        "authorityKeyIdentifier = keyid:always,issuer:always",
    ]
    intermediate_extensions = {
        "basic_constraints_missing": [
            "keyUsage = critical,digitalSignature,keyCertSign,cRLSign",
            "subjectKeyIdentifier = hash",
            "authorityKeyIdentifier = keyid:always,issuer:always",
        ],
        "basic_constraints_noncritical": [
            "basicConstraints = CA:true,pathlen:4",
            "keyUsage = critical,digitalSignature,keyCertSign,cRLSign",
            "subjectKeyIdentifier = hash",
            "authorityKeyIdentifier = keyid:always,issuer:always",
        ],
        "key_usage_missing": [
            "basicConstraints = critical,CA:true,pathlen:4",
            "subjectKeyIdentifier = hash",
            "authorityKeyIdentifier = keyid:always,issuer:always",
        ],
        "key_usage_no_keycertsign": [
            "basicConstraints = critical,CA:true,pathlen:4",
            "keyUsage = critical,digitalSignature,cRLSign",
            "subjectKeyIdentifier = hash",
            "authorityKeyIdentifier = keyid:always,issuer:always",
        ],
        "subject_key_identifier_missing": [
            "basicConstraints = critical,CA:true,pathlen:4",
            "keyUsage = critical,digitalSignature,keyCertSign,cRLSign",
            "subjectKeyIdentifier = hash",
            "authorityKeyIdentifier = keyid:always,issuer:always",
        ],
        "authority_key_identifier_missing": [
            "basicConstraints = critical,CA:true,pathlen:4",
            "keyUsage = critical,digitalSignature,keyCertSign,cRLSign",
            "subjectKeyIdentifier = hash",
        ],
        "pathlen_zero": [
            "basicConstraints = critical,CA:true,pathlen:0",
            "keyUsage = critical,digitalSignature,keyCertSign,cRLSign",
            "subjectKeyIdentifier = hash",
            "authorityKeyIdentifier = keyid:always,issuer:always",
        ],
        "signature_sha1": normal_intermediate,
    }
    intermediate_certificates = {}
    for name, extensions in [("normal", normal_intermediate)] + list(intermediate_extensions.items()):
        certificate = directory / ("intermediate-" + name + ".pem")
        intermediate_certificates[name] = issue_certificate(
            openssl,
            root_state,
            intermediate_request,
            certificate,
            "intermediate_" + name,
            extensions,
            "sha1" if name == "signature_sha1" else "sha256",
        )
    leaf_key, leaf_request = make_key_request(
        openssl, directory, "leaf", "/CN=localhost"
    )
    normal_leaf = [
        "basicConstraints = critical,CA:false",
        "keyUsage = critical,digitalSignature,keyEncipherment",
        "extendedKeyUsage = serverAuth",
        "subjectKeyIdentifier = hash",
        "authorityKeyIdentifier = keyid,issuer",
        "subjectAltName = DNS:localhost",
    ]
    leaf_extensions = {
        "normal": normal_leaf,
        "wrong_san": normal_leaf[:-1] + ["subjectAltName = DNS:wrong.invalid"],
        "no_san": normal_leaf[:-1],
    }
    leaf_certificates = {}
    for name, certificate in intermediate_certificates.items():
        state = ca_state(
            directory,
            certificate,
            intermediate_key,
            "leaf-" + name,
        )
        leaf = directory / ("leaf-" + name + ".pem")
        leaf_certificates[name] = issue_certificate(
            openssl,
            state,
            leaf_request,
            leaf,
            "leaf_" + name,
            normal_leaf,
        )
    missing_extensions = {
        "subject_key_identifier_missing": SUBJECT_KEY_IDENTIFIER_EXTENSION_OID,
        "authority_key_identifier_missing": AUTHORITY_KEY_IDENTIFIER_EXTENSION_OID,
    }
    for name, oid in missing_extensions.items():
        certificate = intermediate_certificates[name]
        certificate.write_bytes(
            remove_certificate_extension(
                certificate.read_bytes(), oid, root_a_key, directory, openssl
            )
        )
    normal_leaf_state = ca_state(
        directory,
        intermediate_certificates["normal"],
        intermediate_key,
        "leaf-normal-variants",
    )
    for name, extensions in leaf_extensions.items():
        if name == "normal":
            leaf_certificates[name] = leaf_certificates["normal"]
            continue
        leaf = directory / ("leaf-" + name + ".pem")
        leaf_certificates[name] = issue_certificate(
            openssl,
            normal_leaf_state,
            leaf_request,
            leaf,
            "leaf_variant_" + name,
            extensions,
        )
    keydata = leaf_key.read_bytes()

    def chain(name: str, intermediate: str, leaf=None) -> str:
        leaf_path = leaf_certificates[leaf or intermediate]
        path = directory / ("chain-" + name + ".pem")
        path.write_bytes(
            leaf_path.read_bytes()
            + intermediate_certificates[intermediate].read_bytes()
            + keydata
        )
        return str(path)

    direct_leaf = issue_certificate(
        openssl,
        root_state,
        leaf_request,
        directory / "issuer-name-root-leaf.pem",
        "issuer_name_root_leaf",
        normal_leaf,
    )
    root_issuer = certificate_fields(pem_der(direct_leaf.read_bytes()))[1]
    root_name_variants = {
        "issuer_name_root_exact_control": root_issuer,
        "issuer_name_root_case_equivalent": name_variant(
            root_issuer, COMMON_NAME_OID, "case"
        ),
        "issuer_name_root_space_equivalent": name_variant(
            root_issuer, ORGANIZATION_NAME_OID, "spaces"
        ),
        "issuer_name_root_string_type_equivalent": name_variant(
            root_issuer, COMMON_NAME_OID, "string_type"
        ),
        "issuer_name_different_same_key_rejected": name_variant(
            root_issuer, COMMON_NAME_OID, "different"
        ),
    }
    issuer_name_chains = {}
    for name, issuer in root_name_variants.items():
        certificate = direct_leaf.read_bytes()
        if name != "issuer_name_root_exact_control":
            certificate = resigned_issuer_certificate(
                certificate, issuer, root_a_key, directory, openssl
            )
        leaf = write_fixture(
            directory / (name + ".pem"), certificate
        )
        chainfile = write_fixture(
            directory / (name + "-chain.pem"), leaf.read_bytes() + keydata
        )
        issuer_name_chains[name] = str(chainfile)

    name_intermediate_key, name_intermediate_request = make_key_request(
        openssl,
        directory,
        "issuer-name-intermediate",
        "/O=RTLS Intermediate CA/CN=RTLS-Name-Intermediate",
    )
    name_intermediate = issue_certificate(
        openssl,
        root_state,
        name_intermediate_request,
        directory / "issuer-name-intermediate.pem",
        "issuer_name_intermediate",
        normal_intermediate,
    )
    name_intermediate_state = ca_state(
        directory,
        name_intermediate,
        name_intermediate_key,
        "issuer-name-leaf",
    )
    name_intermediate_leaf = issue_certificate(
        openssl,
        name_intermediate_state,
        leaf_request,
        directory / "issuer-name-intermediate-leaf.pem",
        "issuer_name_intermediate_leaf",
        normal_leaf,
    )
    intermediate_issuer = certificate_fields(
        pem_der(name_intermediate_leaf.read_bytes())
    )[1]
    intermediate_name_variants = {
        "issuer_name_intermediate_exact_control": intermediate_issuer,
        "issuer_name_intermediate_case_equivalent": name_variant(
            intermediate_issuer, COMMON_NAME_OID, "case"
        ),
        "issuer_name_intermediate_space_equivalent": name_variant(
            intermediate_issuer, ORGANIZATION_NAME_OID, "spaces"
        ),
        "issuer_name_intermediate_string_type_equivalent": name_variant(
            intermediate_issuer, COMMON_NAME_OID, "string_type"
        ),
    }
    for name, issuer in intermediate_name_variants.items():
        certificate = name_intermediate_leaf.read_bytes()
        if name != "issuer_name_intermediate_exact_control":
            certificate = resigned_issuer_certificate(
                certificate, issuer, name_intermediate_key, directory, openssl
            )
        leaf = write_fixture(
            directory / (name + ".pem"), certificate
        )
        chainfile = write_fixture(
            directory / (name + "-chain.pem"),
            leaf.read_bytes() + name_intermediate.read_bytes() + keydata,
        )
        issuer_name_chains[name] = str(chainfile)

    malformed_policy = intermediate_certificates["basic_constraints_noncritical"]
    _, malformed_unrelated_request = make_key_request(
        openssl, directory, "unrelated", "/CN=RTLS-Unrelated"
    )
    unrelated_cert = issue_certificate(
        openssl,
        root_state,
        malformed_unrelated_request,
        directory / "unrelated-malformed-ca.pem",
        "unrelated_malformed_ca",
        [
            "basicConstraints = CA:true,pathlen:0",
            "keyUsage = critical,digitalSignature,keyCertSign,cRLSign",
            "subjectKeyIdentifier = hash",
            "authorityKeyIdentifier = keyid:always,issuer:always",
        ],
    )
    unrelated_chain = directory / "chain-unrelated-malformed.pem"
    unrelated_chain.write_bytes(
        leaf_certificates["normal"].read_bytes()
        + intermediate_certificates["normal"].read_bytes()
        + unrelated_cert.read_bytes()
        + keydata
    )
    duplicate_der = pem_der(malformed_policy.read_bytes())
    duplicate_fields, _, _ = certificate_fields(duplicate_der)
    extensions_offset = next(index for index, item in enumerate(duplicate_fields) if item[0] == 0xa3)
    explicit_extensions = der_children(duplicate_fields[extensions_offset])
    extension_fields = der_children(explicit_extensions[0])
    basic_constraints = next(
        extension
        for extension in extension_fields
        if der_children(extension)[0] == b"\x06\x03\x55\x1d\x13"
    )
    duplicate_fields[extensions_offset] = der_value(
        0xa3,
        der_value(0x30, b"".join(extension_fields + [basic_constraints])),
    )
    duplicate_certificate = resign_certificate(
        duplicate_der,
        duplicate_fields,
        root_a_key,
        directory,
        openssl,
    )
    duplicate_path = write_fixture(
        directory / "intermediate-duplicate-critical.pem",
        certificate_pem(duplicate_certificate),
    )
    duplicate_leaf_state = ca_state(
        directory,
        duplicate_path,
        intermediate_key,
        "leaf-duplicate-critical",
    )
    duplicate_leaf = issue_certificate(
        openssl,
        duplicate_leaf_state,
        leaf_request,
        directory / "leaf-duplicate-critical.pem",
        "leaf_duplicate_critical",
        normal_leaf,
    )
    duplicate_chain = directory / "chain-duplicate-critical.pem"
    duplicate_chain.write_bytes(duplicate_leaf.read_bytes() + duplicate_path.read_bytes() + keydata)

    root_b, root_b_key = make_root_b(openssl, directory)
    cross_key, cross_request = make_key_request(
        openssl, directory, "cross-intermediate", "/CN=RTLS-Cross-Intermediate"
    )
    cross_a = issue_certificate(
        openssl,
        root_state,
        cross_request,
        directory / "cross-a.pem",
        "cross_a",
        normal_intermediate,
    )
    root_b_state = ca_state(directory, root_b, root_b_key, "root-b")
    cross_b = issue_certificate(
        openssl,
        root_b_state,
        cross_request,
        directory / "cross-b.pem",
        "cross_b",
        normal_intermediate,
    )
    cross_state = ca_state(directory, cross_a, cross_key, "cross-leaf")
    cross_leaf = issue_certificate(
        openssl,
        cross_state,
        leaf_request,
        directory / "cross-leaf.pem",
        "cross_leaf",
        normal_leaf,
    )
    cross_chain = directory / "chain-cross-signed.pem"
    cross_chain.write_bytes(cross_leaf.read_bytes() + cross_a.read_bytes() + keydata)
    cross_trust = write_fixture(
        directory / "cross-trust.pem", cross_b.read_bytes() + root_b.read_bytes()
    )
    cross_intermediate_trust = write_fixture(
        directory / "cross-intermediate-trust.pem", cross_b.read_bytes()
    )

    mismatch_fields, _, _ = certificate_fields(pem_der(leaf_certificates["normal"].read_bytes()))
    wrong_issuer = certificate_fields(pem_der(root_b.read_bytes()))[2]
    version_offset = 1 if mismatch_fields[0][0] == 0xa0 else 0
    mismatch_fields[version_offset + 2] = wrong_issuer
    mismatch_der = resign_certificate(
        pem_der(leaf_certificates["normal"].read_bytes()),
        mismatch_fields,
        intermediate_key,
        directory,
        openssl,
    )
    mismatch_leaf = write_fixture(
        directory / "leaf-issuer-subject-mismatch.pem", certificate_pem(mismatch_der)
    )
    mismatch_chain = directory / "chain-issuer-subject-mismatch.pem"
    mismatch_chain.write_bytes(
        mismatch_leaf.read_bytes()
        + intermediate_certificates["normal"].read_bytes()
        + keydata
    )

    path0_key, path0_request = make_key_request(
        openssl, directory, "path0-intermediate", "/CN=RTLS-Path0-Intermediate"
    )
    path0_cert = issue_certificate(
        openssl,
        root_state,
        path0_request,
        directory / "path0-intermediate.pem",
        "path0_intermediate",
        intermediate_extensions["pathlen_zero"],
    )
    subca_key, subca_request = make_key_request(
        openssl, directory, "pathlen-subca", "/CN=RTLS-Pathlen-SubCA"
    )
    path0_state = ca_state(directory, path0_cert, path0_key, "pathlen-subca")
    subca = issue_certificate(
        openssl,
        path0_state,
        subca_request,
        directory / "pathlen-subca.pem",
        "pathlen_subca",
        normal_intermediate,
    )
    subca_state = ca_state(directory, subca, subca_key, "pathlen-leaf")
    pathlen_leaf = issue_certificate(
        openssl,
        subca_state,
        leaf_request,
        directory / "leaf-pathlen.pem",
        "pathlen_leaf",
        normal_leaf,
    )
    pathlen_chain = directory / "chain-pathlen.pem"
    pathlen_chain.write_bytes(pathlen_leaf.read_bytes() + subca.read_bytes() + path0_cert.read_bytes() + keydata)

    self_parent_key, self_parent_request = make_key_request(
        openssl, directory, "self-parent", "/CN=RTLS-Self-Issued"
    )
    self_parent = issue_certificate(
        openssl,
        root_state,
        self_parent_request,
        directory / "self-parent.pem",
        "self_parent",
        intermediate_extensions["pathlen_zero"],
    )
    self_parent_state = ca_state(directory, self_parent, self_parent_key, "self-issued")
    self_issued_key, self_issued_request = make_key_request(
        openssl, directory, "self-issued", "/CN=RTLS-Self-Issued"
    )
    self_issued = issue_certificate(
        openssl,
        self_parent_state,
        self_issued_request,
        directory / "self-issued.pem",
        "self_issued",
        intermediate_extensions["pathlen_zero"],
    )
    self_issued_state = ca_state(directory, self_issued, self_issued_key, "self-issued-leaf")
    self_issued_leaf = issue_certificate(
        openssl,
        self_issued_state,
        leaf_request,
        directory / "leaf-self-issued.pem",
        "leaf_self_issued",
        normal_leaf,
    )
    self_issued_chain = directory / "chain-self-issued.pem"
    self_issued_chain.write_bytes(
        self_issued_leaf.read_bytes()
        + self_issued.read_bytes()
        + self_parent.read_bytes()
        + keydata
    )
    self_issued_subject = certificate_fields(pem_der(self_issued.read_bytes()))[2]
    canonical_self_issued = write_fixture(
        directory / "self-issued-canonical-name.pem",
        resigned_issuer_certificate(
            self_issued.read_bytes(),
            name_variant(self_issued_subject, COMMON_NAME_OID, "case"),
            self_parent_key,
            directory,
            openssl,
        ),
    )
    canonical_self_issued_chain = write_fixture(
        directory / "chain-self-issued-canonical-name.pem",
        self_issued_leaf.read_bytes()
        + canonical_self_issued.read_bytes()
        + self_parent.read_bytes()
        + keydata,
    )

    constrained_key, constrained_request = make_key_request(
        openssl, directory, "name-constrained-ca", "/CN=RTLS-Name-Constrained-CA"
    )
    constrained_ca = issue_certificate(
        openssl,
        root_state,
        constrained_request,
        directory / "name-constrained-ca.pem",
        "name_constrained_ca",
        [
            "basicConstraints = critical,CA:true,pathlen:0",
            "keyUsage = critical,keyCertSign,cRLSign",
            "subjectKeyIdentifier = hash",
            "authorityKeyIdentifier = keyid:always,issuer",
            "nameConstraints = critical,permitted;DNS:.allowed.invalid",
        ],
    )

    def constrained_chain(name: str, common_name: str, san=None) -> str:
        leaf_key, request = make_key_request(
            openssl, directory, "name-constrained-leaf-" + name, "/CN=" + common_name
        )
        state = ca_state(
            directory,
            constrained_ca,
            constrained_key,
            "name-constrained-leaf-" + name,
        )
        extensions = [
            "basicConstraints = critical,CA:false",
            "keyUsage = critical,digitalSignature,keyEncipherment",
            "extendedKeyUsage = serverAuth",
            "subjectKeyIdentifier = hash",
            "authorityKeyIdentifier = keyid,issuer",
        ]
        if san is not None:
            extensions.append("subjectAltName = DNS:" + san)
        certificate = issue_certificate(
            openssl,
            state,
            request,
            directory / ("name-constrained-leaf-" + name + ".pem"),
            "name_constrained_leaf_" + name,
            extensions,
        )
        chainfile = directory / ("chain-name-constrained-" + name + ".pem")
        chainfile.write_bytes(
            certificate.read_bytes() + constrained_ca.read_bytes() + leaf_key.read_bytes()
        )
        return str(chainfile)

    constrained_chains = {
        "allowed_cn": constrained_chain(
            "allowed-cn", "service.allowed.invalid"
        ),
        "blocked_cn": constrained_chain("blocked-cn", "blocked.invalid"),
        "blocked_cn_san": constrained_chain(
            "blocked-cn-san", "blocked.invalid", "service.allowed.invalid"
        ),
    }

    wildcard_ca_state = ca_state(directory, root_a, root_a_key, "wildcard-leaf")
    wildcard_chains = {}
    for name, common_name in (
        ("single_suffix", "*.invalid"),
        ("multi_suffix_control", "*.a.invalid"),
        ("idna_public_suffix", "*.xn--p1ai"),
    ):
        wildcard_key, wildcard_request = make_key_request(
            openssl, directory, "wildcard-" + name, "/CN=" + common_name
        )
        wildcard_cert = issue_certificate(
            openssl,
            wildcard_ca_state,
            wildcard_request,
            directory / ("wildcard-" + name + ".pem"),
            "wildcard_leaf_" + name,
            [
                "basicConstraints = critical,CA:false",
                "keyUsage = critical,digitalSignature,keyEncipherment",
                "extendedKeyUsage = serverAuth",
                "subjectKeyIdentifier = hash",
                "authorityKeyIdentifier = keyid,issuer",
            ],
        )
        wildcard_chain = directory / ("chain-wildcard-" + name + ".pem")
        wildcard_chain.write_bytes(wildcard_cert.read_bytes() + wildcard_key.read_bytes())
        wildcard_chains[name] = str(wildcard_chain)

    aia_root, aia_root_key = make_policy_root(
        openssl,
        directory,
        "Critical-AIA-Root",
        [
            "basicConstraints = critical,CA:true,pathlen:5",
            "keyUsage = critical,keyCertSign,cRLSign",
            "subjectKeyIdentifier = hash",
            "authorityKeyIdentifier = keyid:always,issuer",
            "authorityInfoAccess = critical,OCSP;URI:http://ocsp.example.invalid",
        ],
    )
    aia_ca_state = ca_state(directory, aia_root, aia_root_key, "critical-aia-root")
    aia_leaf = issue_certificate(
        openssl,
        aia_ca_state,
        leaf_request,
        directory / "critical-aia-leaf.pem",
        "critical_aia_leaf",
        normal_leaf,
    )
    aia_chain = write_fixture(
        directory / "chain-critical-aia.pem", aia_leaf.read_bytes() + keydata
    )

    ns_cert_type_leaf = issue_certificate(
        openssl,
        normal_leaf_state,
        leaf_request,
        directory / "leaf-ns-cert-type-client.pem",
        "ns_cert_type_client_leaf",
        normal_leaf + ["nsCertType = client"],
    )
    ns_cert_type_chain = write_fixture(
        directory / "chain-ns-cert-type-client.pem",
        ns_cert_type_leaf.read_bytes()
        + intermediate_certificates["normal"].read_bytes()
        + keydata,
    )

    trust_root = str(root_a)
    path_cases = []
    strict_names = [
        ("basic_constraints_missing", "basic_constraints_missing"),
        ("basic_constraints_noncritical", "basic_constraints_noncritical"),
        ("key_usage_missing", "key_usage_missing"),
        ("key_usage_no_keycertsign", "key_usage_no_keycertsign"),
        ("subject_key_identifier_missing", "subject_key_identifier_missing"),
        ("authority_key_identifier_missing", "authority_key_identifier_missing"),
        ("signature_sha1", "signature_sha1"),
    ]
    for case_name, fixture_name in strict_names:
        chainfile = chain(case_name, fixture_name)
        for suffix, flags in (("", {}), ("_disabled", {"VERIFY_X509_STRICT": False})):
            case = {
                "name": "strict_" + case_name + suffix,
                "chainfile": chainfile,
                "trustfile": trust_root,
                "flags": flags,
            }
            if fixture_name == "signature_sha1":
                case["server_ciphers"] = "DEFAULT:@SECLEVEL=0"
            path_cases.append(case)
    for name, chainfile in issuer_name_chains.items():
        path_cases.append(
            {
                "name": name,
                "chainfile": chainfile,
                "trustfile": trust_root,
            }
        )
    path_cases.extend(
        [
            {
                "name": "strict_pathlen_exceeded",
                "chainfile": str(pathlen_chain),
                "trustfile": trust_root,
            },
            {
                "name": "strict_issuer_subject_mismatch",
                "chainfile": str(mismatch_chain),
                "trustfile": trust_root,
            },
            {
                "name": "hostname_wrong_san",
                "chainfile": chain("wrong-san", "normal", "wrong_san"),
                "trustfile": trust_root,
            },
            {
                "name": "hostname_cn_without_san",
                "chainfile": chain("no-san", "normal", "no_san"),
                "trustfile": trust_root,
            },
            {
                "name": "name_constraints_allowed_cn",
                "chainfile": constrained_chains["allowed_cn"],
                "trustfile": trust_root,
                "hostname": "service.allowed.invalid",
            },
            {
                "name": "name_constraints_blocked_cn",
                "chainfile": constrained_chains["blocked_cn"],
                "trustfile": trust_root,
                "hostname": "blocked.invalid",
            },
            {
                "name": "name_constraints_blocked_cn_check_hostname_disabled",
                "chainfile": constrained_chains["blocked_cn"],
                "trustfile": trust_root,
                "hostname": "blocked.invalid",
                "check_hostname": False,
            },
            {
                "name": "name_constraints_blocked_cn_common_name_disabled",
                "chainfile": constrained_chains["blocked_cn"],
                "trustfile": trust_root,
                "hostname": "blocked.invalid",
                "check_hostname": False,
                "hostname_checks_common_name": False,
            },
            {
                "name": "name_constraints_blocked_cn_common_name_disabled_hostname",
                "chainfile": constrained_chains["blocked_cn"],
                "trustfile": trust_root,
                "hostname": "blocked.invalid",
                "hostname_checks_common_name": False,
            },
            {
                "name": "name_constraints_san_dns_precedence_allowed",
                "chainfile": constrained_chains["blocked_cn_san"],
                "trustfile": trust_root,
                "hostname": "service.allowed.invalid",
            },
            {
                "name": "name_constraints_san_dns_precedence_blocked",
                "chainfile": constrained_chains["blocked_cn_san"],
                "trustfile": trust_root,
                "hostname": "blocked.invalid",
            },
            {
                "name": "hostname_wildcard_single_suffix",
                "chainfile": wildcard_chains["single_suffix"],
                "trustfile": trust_root,
                "hostname": "foo.invalid",
            },
            {
                "name": "hostname_wildcard_multi_suffix_control",
                "chainfile": wildcard_chains["multi_suffix_control"],
                "trustfile": trust_root,
                "hostname": "foo.a.invalid",
            },
            {
                "name": "hostname_wildcard_idna_public_suffix",
                "chainfile": wildcard_chains["idna_public_suffix"],
                "trustfile": trust_root,
                "hostname": "foo.xn--p1ai",
            },
            {
                "name": "strict_duplicate_critical_extension",
                "chainfile": str(duplicate_chain),
                "trustfile": trust_root,
            },
            {
                "name": "strict_duplicate_critical_extension_disabled",
                "chainfile": str(duplicate_chain),
                "trustfile": trust_root,
                "flags": {"VERIFY_X509_STRICT": False},
            },
            {
                "name": "critical_aia_on_trust_root",
                "chainfile": str(aia_chain),
                "trustfile": str(aia_root),
            },
            {
                "name": "ns_cert_type_client_on_server_leaf",
                "chainfile": str(ns_cert_type_chain),
                "trustfile": trust_root,
            },
            {
                "name": "unrelated_malformed_peer_certificate",
                "chainfile": str(unrelated_chain),
                "trustfile": trust_root,
            },
            {
                "name": "self_issued_not_self_signed_pathlen",
                "chainfile": str(self_issued_chain),
                "trustfile": trust_root,
            },
            {
                "name": "self_issued_canonical_name_pathlen",
                "chainfile": str(canonical_self_issued_chain),
                "trustfile": trust_root,
            },
            {
                "name": "cross_signed_trusted_first_enabled",
                "chainfile": str(cross_chain),
                "trustfile": str(cross_trust),
                "flags": {
                    "VERIFY_X509_PARTIAL_CHAIN": False,
                    "VERIFY_X509_TRUSTED_FIRST": True,
                },
            },
            {
                "name": "cross_signed_trusted_first_disabled",
                "chainfile": str(cross_chain),
                "trustfile": str(cross_trust),
                "flags": {
                    "VERIFY_X509_PARTIAL_CHAIN": False,
                    "VERIFY_X509_TRUSTED_FIRST": False,
                },
            },
            {
                "name": "trusted_intermediate_partial_chain_enabled",
                "chainfile": str(cross_chain),
                "trustfile": str(cross_intermediate_trust),
            },
            {
                "name": "trusted_intermediate_partial_chain_disabled",
                "chainfile": str(cross_chain),
                "trustfile": str(cross_intermediate_trust),
                "flags": {"VERIFY_X509_PARTIAL_CHAIN": False},
            },
        ]
    )
    path_cases.extend(
        make_eku_policy_cases(
            certdata, directory, openssl, normal_intermediate
        )
    )
    return path_cases, {
        "root": str(root_a),
        "root_b": str(root_b),
        "duplicate_critical_chain": str(duplicate_chain),
        "critical_aia_root": str(aia_root),
        "ns_cert_type_client_chain": str(ns_cert_type_chain),
        "openssl": openssl,
    }


def make_manifest(certdata: Path, directory: Path, openssl: str) -> Path:
    source = certdata / "keycert3.pem"
    source_data = source.read_bytes()
    source_certificates = cert_blocks(source_data)
    if not source_certificates:
        raise ValueError("keycert3.pem contains no certificate")
    baseline_cert = source_certificates[0] + b"\n"
    baseline_key = private_key(source_data)
    baseline_chain = write_fixture(
        directory / "baseline-chain.pem", baseline_cert + baseline_key
    )
    other_certificates = cert_blocks((certdata / "keycert4.pem").read_bytes())
    if not other_certificates:
        raise ValueError("keycert4.pem contains no certificate")
    malformed = b"-----BEGIN CERTIFICATE-----\nnot-base64\n-----END CERTIFICATE-----\n"
    truncated = b"-----BEGIN CERTIFICATE-----\n" + base64.b64encode(b"\x30\x82\x02") + b"\n-----END CERTIFICATE-----\n"
    malformed_trailing = write_fixture(
        directory / "malformed-trailing.pem",
        baseline_cert + baseline_key + malformed,
    )
    malformed_middle = write_fixture(
        directory / "malformed-middle.pem",
        baseline_cert + malformed + other_certificates[0] + b"\n" + baseline_key,
    )
    malformed_base64 = write_fixture(
        directory / "malformed-base64.pem",
        baseline_cert + b"\n" + malformed + baseline_key,
    )
    malformed_truncated = write_fixture(
        directory / "malformed-truncated-der.pem",
        baseline_cert + b"\n" + truncated + baseline_key,
    )
    surrounding_text = write_fixture(
        directory / "surrounding-text.pem",
        b"certificate fixture preamble\n"
        + baseline_cert
        + b"\n"
        + baseline_key
        + b"\ncertificate fixture ending\n",
    )
    replacement_cert = write_fixture(
        directory / "replacement-cert.pem", other_certificates[0] + b"\n"
    )
    mismatch_cert = write_fixture(
        directory / "mismatched-cert.pem", baseline_cert + b"\n"
    )
    leaf_only_trust = write_fixture(
        directory / "leaf-only-trust.pem", baseline_cert
    )
    load_cases = [
        {"name": "load_valid_chain", "certfile": str(baseline_chain)},
        {"name": "load_malformed_trailing_pem", "certfile": str(malformed_trailing)},
        {"name": "load_malformed_middle_pem", "certfile": str(malformed_middle)},
        {"name": "load_malformed_base64", "certfile": str(malformed_base64)},
        {"name": "load_truncated_der", "certfile": str(malformed_truncated)},
        {"name": "load_surrounding_text", "certfile": str(surrounding_text)},
        {
            "name": "load_mismatched_key",
            "certfile": str(mismatch_cert),
            "keyfile": str(certdata / "ssl_key.pem"),
        },
        {"name": "load_encrypted_key_without_password", "certfile": str(certdata / "keycert.passwd.pem")},
        {
            "name": "load_encrypted_key_correct_password",
            "certfile": str(certdata / "keycert.passwd.pem"),
            "password": "somepass",
        },
        {
            "name": "load_encrypted_key_wrong_password",
            "certfile": str(certdata / "keycert.passwd.pem"),
            "password": "incorrect",
        },
    ]
    root = certdata / "capath" / "ceff1710.0"
    missing_aki_chain = certdata / "leaf-missing-aki.keycert.pem"
    missing_aki_root = certdata / "leaf-missing-aki.ca.pem"
    path_cases = [
        {
            "name": "valid_path",
            "chainfile": str(baseline_chain),
            "trustfile": str(root),
        },
        {
            "name": "strict_missing_aki_default",
            "chainfile": str(missing_aki_chain),
            "trustfile": str(missing_aki_root),
            "hostname": "example.com",
        },
        {
            "name": "strict_missing_aki_disabled",
            "chainfile": str(missing_aki_chain),
            "trustfile": str(missing_aki_root),
            "hostname": "example.com",
            "flags": {"VERIFY_X509_STRICT": False},
        },
        {
            "name": "partial_chain_enabled",
            "chainfile": str(baseline_chain),
            "trustfile": str(leaf_only_trust),
        },
        {
            "name": "partial_chain_disabled",
            "chainfile": str(baseline_chain),
            "trustfile": str(leaf_only_trust),
            "flags": {"VERIFY_X509_PARTIAL_CHAIN": False},
        },
        {
            "name": "trusted_first_disabled",
            "chainfile": str(baseline_chain),
            "trustfile": str(root),
            "flags": {"VERIFY_X509_TRUSTED_FIRST": False},
        },
    ]
    generated_path_cases, generated_fixtures = make_policy_fixtures(
        certdata, directory, openssl
    )
    path_cases.extend(generated_path_cases)
    load_cases.append(
        {
            "name": "load_duplicate_critical_extension",
            "certfile": generated_fixtures["duplicate_critical_chain"],
        }
    )
    atomic_replacement = write_fixture(
        directory / "atomic-replacement.pem",
        replacement_cert.read_bytes() + private_key((certdata / "keycert4.pem").read_bytes()),
    )
    manifest = {
        "load_cases": load_cases,
        "path_cases": path_cases,
        "fixture_generator": generated_fixtures,
        "atomic_case": {
            "baseline_chain": str(baseline_chain),
            "replacement_cert": str(atomic_replacement),
            "mismatched_key": str(certdata / "ssl_key.pem"),
        },
    }
    manifest_path = directory / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True))
    return manifest_path


def run_worker(interpreter: Path, manifest: Path, environment: dict[str, str]) -> dict[str, object]:
    completed = subprocess.run(
        [str(interpreter), "-I", "-B", "-c", WORKER, str(manifest)],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=120,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"worker failed for {interpreter}: {completed.stderr.strip()}"
        )
    return json.loads(completed.stdout)


def comparable(case: dict[str, object], include_flags: bool = True) -> dict[str, object]:
    def normalized(value):
        if isinstance(value, dict):
            return {
                key: normalized(item)
                for key, item in value.items()
                if key != "message"
                and key != "verify_code"
                and key != "hostname_policy"
                and (include_flags or key != "verify_flags")
            }
        if isinstance(value, list):
            return [normalized(item) for item in value]
        return value

    return normalized(case)


def reference_matches_expectation(case: dict[str, object], expected: dict[str, object]) -> bool:
    for name, value in expected.items():
        if name == "error_type":
            actual = (case.get("error") or {}).get("type")
        elif name.startswith("error."):
            actual = (case.get("error") or {}).get(name.split(".", 1)[1])
        elif name == "after_accepted":
            actual = (case.get("after") or {}).get("accepted")
        elif name.startswith("hostname_policy."):
            actual = (case.get("hostname_policy") or {}).get(name.split(".", 1)[1])
        else:
            actual = case.get(name)
        if actual != value:
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--certdata", required=True, type=Path)
    parser.add_argument("--workdir", type=Path, default=Path(".work/tmp"))
    parser.add_argument("--openssl", type=Path)
    args = parser.parse_args()
    reference = args.reference.resolve()
    candidate = args.candidate.resolve()
    certdata = args.certdata.resolve()
    workdir = args.workdir.resolve()
    openssl = str(args.openssl.resolve()) if args.openssl else shutil.which("openssl")
    if openssl is None or not Path(openssl).is_file():
        parser.error("an OpenSSL-compatible command is required to generate fixtures")
    for path in (reference, candidate):
        if not path.is_file() or not os.access(path, os.X_OK):
            parser.error(f"interpreter is not executable: {path}")
    if not certdata.is_dir():
        parser.error(f"certificate data directory is missing: {certdata}")
    workdir.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    for name in ("SSL_CERT_FILE", "SSL_CERT_DIR", "PYTHONHOME", "PYTHONPATH"):
        environment.pop(name, None)
    with tempfile.TemporaryDirectory(prefix="certificate-contract-", dir=workdir) as temporary:
        directory = Path(temporary)
        environment["TMPDIR"] = str(directory)
        manifest = make_manifest(certdata, directory, openssl)
        manifest_data = json.loads(manifest.read_text())
        manifest_data["reference_interpreter"] = str(reference)
        manifest.write_text(json.dumps(manifest_data, sort_keys=True))
        oracle = run_worker(reference, manifest, environment)
        port = run_worker(candidate, manifest, environment)
    if not oracle["backend"].startswith(REFERENCE_BACKEND_PREFIX):
        raise RuntimeError(
            "reference interpreter does not use the pinned backend: " + oracle["backend"]
        )
    case_names = sorted(set(oracle["cases"]) | set(port["cases"]))
    differences = []
    flag_differences = []
    cases = {}
    harness_errors = []
    for runtime, results in (("reference", oracle), ("candidate", port)):
        for name, case in results["cases"].items():
            if "harness_error" in case:
                harness_errors.append(
                    {
                        "runtime": runtime,
                        "case": name,
                        "phase": case.get("phase"),
                        "error": case["harness_error"],
                    }
                )
            if name in results["path_case_names"] and case.get("accepted") is False:
                error = case.get("error") or {}
                if case.get("phase") != "handshake" or error.get("type") != "SSLCertVerificationError":
                    harness_errors.append(
                        {
                            "runtime": runtime,
                            "case": name,
                            "phase": case.get("phase"),
                            "error": case.get("harness_error") or case.get("error"),
                            "expected": "SSLCertVerificationError during completed handshake",
                        }
                    )
    reference_expectation_errors = []
    for name, expected in REFERENCE_EXPECTATIONS.items():
        reference_case = oracle["cases"].get(name)
        if reference_case is None or not reference_matches_expectation(reference_case, expected):
            reference_expectation_errors.append(
                {
                    "case": name,
                    "expected": expected,
                    "actual": reference_case,
                }
            )
    default_flags_differ = comparable(oracle["default_verify_flags"]) != comparable(
        port["default_verify_flags"]
    )
    if default_flags_differ:
        differences.append("default_verify_flags")
    for name in case_names:
        reference_case = oracle["cases"].get(name)
        candidate_case = port["cases"].get(name)
        oracle_differs = comparable(reference_case, include_flags=False) != comparable(
            candidate_case, include_flags=False
        )
        flags_differ = comparable(reference_case.get("verify_flags")) != comparable(
            candidate_case.get("verify_flags")
        )
        intentional_difference = name in {
            "failed_load_identity_atomicity",
            "load_duplicate_critical_extension",
        }
        if name == "failed_load_identity_atomicity":
            contract_passed = (
                not candidate_case["accepted"]
                and (candidate_case.get("error") or {}).get("type") == "SSLError"
                and candidate_case["identity_preserved"]
            )
        elif name == "load_duplicate_critical_extension":
            contract_passed = (
                reference_case["accepted"]
                and not candidate_case["accepted"]
                and (candidate_case.get("error") or {}).get("type") == "SSLError"
            )
        else:
            contract_passed = not oracle_differs
        if name in oracle["path_case_names"] and reference_case.get("accepted") is False:
            candidate_error = candidate_case.get("error") or {}
            contract_passed = (
                contract_passed
                and candidate_case.get("phase") == "handshake"
                and candidate_error.get("type") == "SSLCertVerificationError"
            )
        expected_verify_code = REFERENCE_EXPECTATIONS.get(name, {}).get("error.verify_code")
        candidate_error = candidate_case.get("error") or {}
        verify_code_matches_expected = (
            expected_verify_code is None
            or candidate_error.get("verify_code") == expected_verify_code
        )
        behavior_different = (oracle_differs and not intentional_difference) or not verify_code_matches_expected
        different = (
            not contract_passed
            or (flags_differ and not intentional_difference)
            or not verify_code_matches_expected
        )
        if behavior_different:
            differences.append(name)
        if flags_differ:
            flag_differences.append(name)
        cases[name] = {
            "reference": reference_case,
            "candidate": candidate_case,
            "reference_expected": REFERENCE_EXPECTATIONS.get(name),
            "reference_matches_expected": (
                reference_matches_expectation(reference_case, REFERENCE_EXPECTATIONS[name])
                if name in REFERENCE_EXPECTATIONS and reference_case is not None
                else None
            ),
            "verify_code_expected": expected_verify_code,
            "verify_code_matches_expected": verify_code_matches_expected,
            "matches_reference": not oracle_differs,
            "behavior_different": behavior_different,
            "flags_differ": flags_differ,
            "intentional_difference": (
                "a rejected certificate and key load preserves the previously installed identity"
                if name == "failed_load_identity_atomicity"
                else "the candidate rejects a duplicate critical extension while loading PEM, before path verification"
                if name == "load_duplicate_critical_extension"
                else None
            ),
            "contract_passed": contract_passed,
            "different": different,
        }
    report = {
        "reference": {
            "interpreter": oracle["interpreter"],
            "executable": oracle["executable"],
            "backend": oracle["backend"],
            "default_verify_flags": oracle["default_verify_flags"],
            "expected_backend_prefix": REFERENCE_BACKEND_PREFIX,
        },
        "candidate": {
            "interpreter": port["interpreter"],
            "executable": port["executable"],
            "backend": port["backend"],
            "default_verify_flags": port["default_verify_flags"],
        },
        "fixture_generator": {
            "command": openssl,
            "version": subprocess.run(
                [openssl, "version"], capture_output=True, text=True, check=True
            ).stdout.strip(),
        },
        "cases": cases,
        "default_flags_differ": default_flags_differ,
        "differences": differences,
        "flag_differences": flag_differences,
        "harness_errors": harness_errors,
        "reference_expectation_errors": reference_expectation_errors,
        "result": "passed"
        if not differences
        and not flag_differences
        and not default_flags_differ
        and not harness_errors
        and not reference_expectation_errors
        else "different",
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return (
        1
        if differences
        or flag_differences
        or default_flags_differ
        or harness_errors
        or reference_expectation_errors
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
