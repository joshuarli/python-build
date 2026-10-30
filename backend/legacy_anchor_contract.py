from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
from pathlib import Path

WORKER = r'''
import importlib.util
import json
import ssl
import sys

root, reference, server_cert, contract_path, backend = sys.argv[1:6]
spec = importlib.util.spec_from_file_location("certificate_contract", contract_path)
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)
namespace = {}
exec(contract.WORKER.rsplit("main()", 1)[0], namespace)
context = ssl.create_default_context(cafile=root)
context.verify_flags &= ~ssl.VERIFY_X509_PARTIAL_CHAIN
expected_flags = ssl.VERIFY_X509_STRICT | ssl.VERIFY_X509_TRUSTED_FIRST
if context.verify_flags != expected_flags:
    raise AssertionError(f"unexpected verification flags: {context.verify_flags}")
outcome = namespace["exchange_reference_server"](
    reference, server_cert, None, context, "localhost"
)
print(json.dumps({
    "backend": backend,
    "openssl_version": getattr(ssl, "OPENSSL_VERSION", None),
    "verify_flags": int(context.verify_flags),
    "outcome": outcome,
}, sort_keys=True))
'''


def altered_signature_pem(certificate: bytes) -> bytes:
    begin = b"-----BEGIN CERTIFICATE-----"
    end = b"-----END CERTIFICATE-----"
    if certificate.count(begin) != 1 or certificate.count(end) != 1:
        raise ValueError("expected one PEM certificate")
    body = certificate.split(begin, 1)[1].split(end, 1)[0]
    der = bytearray(base64.b64decode(b"".join(body.split()), validate=True))
    if not der:
        raise ValueError("empty certificate DER")
    der[-1] ^= 1
    encoded = base64.b64encode(der)
    lines = b"\n".join(encoded[index : index + 64] for index in range(0, len(encoded), 64))
    return begin + b"\n" + lines + b"\n" + end + b"\n"


def run_backend(
    interpreter: Path,
    backend: str,
    root: Path,
    reference: Path,
    server_cert: Path,
    workdir: Path,
) -> dict[str, object]:
    environment = os.environ.copy()
    for name in (
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE",
    ):
        environment.pop(name, None)
    environment["TMPDIR"] = str(workdir)
    command = [
        str(interpreter),
        "-I",
        "-B",
        "-c",
        WORKER,
        str(root),
        str(reference),
        str(server_cert),
        str(Path(__file__).with_name("certificate_contract.py").resolve()),
        backend,
    ]
    completed = subprocess.run(
        command,
        cwd=workdir,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
        timeout=90,
    )
    if completed.returncode:
        raise RuntimeError(f"{backend} probe failed: {completed.stderr.strip()}")
    return json.loads(completed.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--certdata", required=True, type=Path)
    parser.add_argument("--workdir", type=Path, default=Path(".work/tmp/legacy-anchor-contract"))
    args = parser.parse_args()
    reference = args.reference.resolve()
    candidate = args.candidate.resolve()
    certdata = args.certdata.resolve()
    workdir = args.workdir.resolve()
    for interpreter in (reference, candidate):
        if not interpreter.is_file() or not os.access(interpreter, os.X_OK):
            parser.error(f"interpreter is not executable: {interpreter}")
    server_cert = certdata / "keycert3.pem"
    if not server_cert.is_file():
        parser.error(f"server certificate is missing: {server_cert}")
    root = Path(__file__).with_name("testdata").joinpath("sha1-root.pem").resolve()
    if not root.is_file():
        parser.error(f"SHA1 root fixture is missing: {root}")
    workdir.mkdir(parents=True, exist_ok=True)
    altered_root = workdir / "sha1-root-altered-signature.pem"
    altered_root.write_bytes(altered_signature_pem(root.read_bytes()))
    outcomes = {
        "reference_valid": run_backend(
            reference, "reference", root, reference, server_cert, workdir
        ),
        "reference_altered": run_backend(
            reference, "reference", altered_root, reference, server_cert, workdir
        ),
        "candidate_valid": run_backend(
            candidate, "candidate", root, reference, server_cert, workdir
        ),
        "candidate_altered": run_backend(
            candidate, "candidate", altered_root, reference, server_cert, workdir
        ),
    }
    if not outcomes["reference_valid"]["openssl_version"].startswith("OpenSSL 3.5.7"):
        raise RuntimeError("reference interpreter is not pinned OpenSSL 3.5.7")
    expected = {
        "reference_valid": True,
        "reference_altered": True,
        "candidate_valid": True,
        "candidate_altered": False,
    }
    actual = {name: result["outcome"]["accepted"] for name, result in outcomes.items()}
    if actual != expected:
        raise AssertionError(
            json.dumps(
                {"expected": expected, "actual": actual, "results": outcomes},
                sort_keys=True,
            )
        )
    peer_hashes = {
        outcomes[name]["outcome"]["peer_sha256"]
        for name in ("reference_valid", "reference_altered", "candidate_valid")
    }
    if len(peer_hashes) != 1:
        raise AssertionError("the valid-handshake cases did not see the same server certificate")
    print(json.dumps({"expected": expected, "results": outcomes}, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
