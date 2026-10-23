from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


WORKER = r'''
import hashlib
import json
import socket
import ssl
import sys
import threading
from pathlib import Path


def error_value(error):
    return {"type": type(error).__name__, "message": str(error)}


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


def load_context(certfile, keyfile=None, password=None):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(
        str(certfile), str(keyfile) if keyfile else None, password=password
    )
    return context


def client_context(cafile, changes):
    context = ssl.create_default_context(cafile=str(cafile))
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


def exchange(server_context, client_context, hostname):
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
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
            raw.settimeout(5)
            with client_context.wrap_socket(raw, server_hostname=hostname) as peer:
                certificate = peer.getpeercert(binary_form=True)
                return {
                    "accepted": True,
                    "peer_sha256": hashlib.sha256(certificate).hexdigest(),
                    "error": None,
                }
    except BaseException as error:
        return {"accepted": False, "peer_sha256": None, "error": error_value(error)}
    finally:
        thread.join(6)
        if thread.is_alive():
            raise TimeoutError("TLS server did not finish")


def run_load_case(case):
    try:
        load_context(
            case["certfile"],
            case.get("keyfile"),
            case.get("password"),
        )
        return {"accepted": True, "error": None, "verify_flags": None}
    except BaseException as error:
        return {
            "accepted": False,
            "error": error_value(error),
            "verify_flags": None,
        }


def run_path_case(case):
    try:
        server = load_context(case["chainfile"])
        client = client_context(case["trustfile"], case.get("flags", {}))
        flags = verify_flags(client)
        result = exchange(server, client, case.get("hostname", "localhost"))
        result["verify_flags"] = flags
        return result
    except BaseException as error:
        return {
            "accepted": False,
            "peer_sha256": None,
            "error": error_value(error),
            "verify_flags": None,
        }


def run_atomic_case(case):
    try:
        server = load_context(case["baseline_chain"])
        before_client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        before_client.check_hostname = False
        before_client.verify_mode = ssl.CERT_NONE
        before = exchange(server, before_client, "localhost")
    except BaseException as error:
        return {
            "accepted": False,
            "error": error_value(error),
            "before": None,
            "after": None,
            "identity_preserved": False,
        }
    try:
        server.load_cert_chain(case["replacement_cert"], case["mismatched_key"])
        failure = None
    except BaseException as error:
        failure = error_value(error)
    after_client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    after_client.check_hostname = False
    after_client.verify_mode = ssl.CERT_NONE
    after = exchange(server, after_client, "localhost")
    return {
        "accepted": failure is None,
        "error": failure,
        "before": before,
        "after": after,
        "identity_preserved": (
            before["accepted"]
            and after["accepted"]
            and before["peer_sha256"] == after["peer_sha256"]
        ),
    }


def main():
    manifest = json.loads(Path(sys.argv[1]).read_text())
    initial = ssl.create_default_context()
    results = {
        "interpreter": sys.version.split()[0],
        "backend": getattr(ssl, "OPENSSL_VERSION", getattr(ssl, "__version__", "unknown")),
        "default_verify_flags": verify_flags(initial),
        "cases": {},
    }
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


def make_manifest(certdata: Path, directory: Path) -> Path:
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
    atomic_replacement = write_fixture(
        directory / "atomic-replacement.pem",
        replacement_cert.read_bytes() + private_key((certdata / "keycert4.pem").read_bytes()),
    )
    manifest = {
        "load_cases": load_cases,
        "path_cases": path_cases,
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
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"worker failed for {interpreter}: {completed.stderr.strip()}"
        )
    return json.loads(completed.stdout)


def comparable(case: dict[str, object]) -> dict[str, object]:
    def normalized(value):
        if isinstance(value, dict):
            return {
                key: normalized(item)
                for key, item in value.items()
                if key != "message"
            }
        if isinstance(value, list):
            return [normalized(item) for item in value]
        return value

    return normalized(case)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--certdata", required=True, type=Path)
    parser.add_argument("--workdir", type=Path, default=Path(".work/tmp"))
    args = parser.parse_args()
    reference = args.reference.resolve()
    candidate = args.candidate.resolve()
    certdata = args.certdata.resolve()
    workdir = args.workdir.resolve()
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
        manifest = make_manifest(certdata, directory)
        oracle = run_worker(reference, manifest, environment)
        port = run_worker(candidate, manifest, environment)
    case_names = sorted(set(oracle["cases"]) | set(port["cases"]))
    differences = []
    cases = {}
    default_flags_differ = comparable(oracle["default_verify_flags"]) != comparable(
        port["default_verify_flags"]
    )
    if default_flags_differ:
        differences.append("default_verify_flags")
    for name in case_names:
        reference_case = oracle["cases"].get(name)
        candidate_case = port["cases"].get(name)
        different = comparable(reference_case) != comparable(candidate_case)
        if different:
            differences.append(name)
        cases[name] = {
            "reference": reference_case,
            "candidate": candidate_case,
            "different": different,
        }
    report = {
        "reference": {
            "interpreter": oracle["interpreter"],
            "backend": oracle["backend"],
            "default_verify_flags": oracle["default_verify_flags"],
        },
        "candidate": {
            "interpreter": port["interpreter"],
            "backend": port["backend"],
            "default_verify_flags": port["default_verify_flags"],
        },
        "cases": cases,
        "default_flags_differ": default_flags_differ,
        "differences": differences,
        "result": "passed" if not differences else "different",
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if differences else 0


if __name__ == "__main__":
    raise SystemExit(main())
