from __future__ import annotations

import argparse
import asyncio
import hashlib
import http.server
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import urllib.request
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def environment(values: dict[str, str | None]):
    previous = {name: os.environ.get(name) for name in values}
    for name, value in values.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def make_expired_certificate(certdata: Path, destination: Path) -> tuple[Path, Path]:
    openssl = shutil.which("openssl")
    if openssl is None:
        raise RuntimeError("an OpenSSL-compatible CLI is required for the expiry fixture")
    destination.mkdir(parents=True)
    newcerts = destination / "newcerts"
    newcerts.mkdir()
    ca_cert = certdata / "pycacert.pem"
    ca_key = certdata / "pycakey.pem"
    leaf_key = destination / "leaf.key"
    request = destination / "leaf.csr"
    certificate = destination / "leaf.pem"
    database = destination / "index.txt"
    serial = destination / "serial"
    database.write_text("")
    serial.write_text("01\n")
    config = destination / "openssl.cnf"
    config.write_text(
        "\n".join(
            (
                "[ca]",
                "default_ca = ca_default",
                "[ca_default]",
                f"database = {database}",
                f"new_certs_dir = {newcerts}",
                f"certificate = {ca_cert}",
                f"private_key = {ca_key}",
                f"serial = {serial}",
                "default_md = sha256",
                "default_days = 365",
                "policy = policy_anything",
                "[policy_anything]",
                "commonName = supplied",
                "[leaf_ext]",
                "basicConstraints = critical,CA:FALSE",
                "keyUsage = critical,digitalSignature,keyEncipherment",
                "extendedKeyUsage = serverAuth",
                "subjectAltName = DNS:localhost",
                "authorityKeyIdentifier = keyid,issuer",
                "",
            )
        )
    )
    subprocess.run(
        [
            openssl,
            "req",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(leaf_key),
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost",
            "-out",
            str(request),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        [
            openssl,
            "ca",
            "-batch",
            "-config",
            str(config),
            "-in",
            str(request),
            "-startdate",
            "100101000000Z",
            "-enddate",
            "100102000000Z",
            "-extensions",
            "leaf_ext",
            "-out",
            str(certificate),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return certificate, leaf_key


def client_context(ssl, cafile: Path | None = None):
    context = ssl.create_default_context(cafile=str(cafile) if cafile else None)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.maximum_version = ssl.TLSVersion.TLSv1_3
    return context


def server_context(ssl, certificate: Path, key: Path | None = None):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.maximum_version = ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(str(certificate), str(key) if key else None)
    return context


def tls_exchange(
    ssl,
    certfile: Path,
    cafile: Path | None,
    *,
    hostname: str = "localhost",
    keyfile: Path | None = None,
    client_context_factory=None,
) -> str:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(5)
    port = listener.getsockname()[1]
    server_errors: list[BaseException] = []
    server_tls = server_context(ssl, certfile, keyfile)

    def serve() -> None:
        try:
            raw, _ = listener.accept()
            raw.settimeout(5)
            with server_tls.wrap_socket(raw, server_side=True) as peer:
                if peer.recv(4) != b"ping":
                    raise AssertionError("server received an unexpected payload")
                peer.sendall(b"pong")
        except BaseException as error:
            server_errors.append(error)
        finally:
            listener.close()

    thread = threading.Thread(target=serve)
    thread.start()
    try:
        client_tls = (
            client_context_factory()
            if client_context_factory is not None
            else client_context(ssl, cafile)
        )
        with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
            with client_tls.wrap_socket(raw, server_hostname=hostname) as peer:
                peer.sendall(b"ping")
                if peer.recv(4) != b"pong":
                    raise AssertionError("client received an unexpected payload")
                if peer.version() != "TLSv1.3":
                    raise AssertionError(f"unexpected protocol: {peer.version()}")
                if not peer.getpeercert():
                    raise AssertionError("client received no verified peer certificate")
        result = "accepted"
    except (OSError, ssl.SSLError) as error:
        result = f"rejected: {type(error).__name__}: {error}"
    finally:
        thread.join(6)
    if thread.is_alive():
        raise TimeoutError("TLS server did not finish")
    if result == "accepted" and server_errors:
        raise server_errors[0]
    return result


def load_malformed_chain(ssl, certdata: Path, directory: Path) -> str:
    chain = directory / "malformed-chain.pem"
    chain.write_bytes(
        (certdata / "keycert3.pem").read_bytes()
        + b"\n-----BEGIN CERTIFICATE-----\nnot-base64\n-----END CERTIFICATE-----\n"
    )
    try:
        server_context(ssl, chain)
    except (OSError, ssl.SSLError, ValueError) as error:
        return f"rejected: {type(error).__name__}: {error}"
    return "accepted"


class TLSHTTPServer(http.server.ThreadingHTTPServer):
    def __init__(self, address, context):
        self.tls_context = context
        super().__init__(address, TLSRequestHandler)

    def get_request(self):
        raw, address = super().get_request()
        return self.tls_context.wrap_socket(raw, server_side=True), address


class TLSRequestHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"https-ok")

    def log_message(self, format, *args):
        pass


def https_default_context(ssl, certdata: Path, mode: str) -> str:
    server = TLSHTTPServer(
        ("127.0.0.1", 0), server_context(ssl, certdata / "keycert3.pem")
    )
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    if mode == "openssl":
        overrides = {
            "SSL_CERT_FILE": str(certdata / "capath" / "ceff1710.0"),
            "SSL_CERT_DIR": None,
            "PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE": None,
        }
    else:
        overrides = {
            "SSL_CERT_FILE": None,
            "SSL_CERT_DIR": None,
            "PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE": None,
        }
    try:
        with environment(overrides):
            with urllib.request.urlopen(
                f"https://localhost:{server.server_port}/", timeout=5
            ) as response:
                if response.status != 200 or response.read() != b"https-ok":
                    raise AssertionError("HTTPS response did not match")
        return "passed"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(6)
        if thread.is_alive():
            raise TimeoutError("HTTPS server did not finish")


async def asyncio_default_context(ssl, certdata: Path, mode: str) -> None:
    async def serve(reader, writer):
        payload = await reader.readexactly(4)
        writer.write(payload[::-1])
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(
        serve,
        "127.0.0.1",
        0,
        ssl=server_context(ssl, certdata / "keycert3.pem"),
        ssl_handshake_timeout=5,
    )
    port = server.sockets[0].getsockname()[1]
    if mode == "openssl":
        overrides = {
            "SSL_CERT_FILE": str(certdata / "capath" / "ceff1710.0"),
            "SSL_CERT_DIR": None,
            "PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE": None,
        }
    else:
        overrides = {
            "SSL_CERT_FILE": None,
            "SSL_CERT_DIR": None,
            "PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE": None,
        }
    try:
        with environment(overrides):
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    "127.0.0.1", port, ssl=True, server_hostname="localhost"
                ),
                5,
            )
            writer.write(b"abcd")
            await writer.drain()
            payload = await asyncio.wait_for(reader.readexactly(4), 5)
            if payload != b"dcba":
                raise AssertionError(f"unexpected asyncio payload: {payload!r}")
            writer.close()
            await writer.wait_closed()
    finally:
        server.close()
        await server.wait_closed()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("certdata", type=Path)
    parser.add_argument("--openssl-reference", action="store_true")
    args = parser.parse_args()
    certdata = args.certdata.resolve()
    ssl = __import__("ssl")
    results: dict[str, object] = {}
    failures: list[str] = []

    if args.openssl_reference:
        if not ssl.OPENSSL_VERSION.startswith("OpenSSL 3.5.7"):
            raise RuntimeError(f"unexpected OpenSSL baseline: {ssl.OPENSSL_VERSION}")
        mode = "openssl"
    else:
        native_ssl = importlib.util.find_spec("_ssl")
        if native_ssl is not None:
            import _ssl

            if not getattr(_ssl, "_RUSTLS_BACKEND", False):
                raise RuntimeError("candidate interpreter still contains CPython's _ssl")
        import _hashlib

        if hashlib.sha256(b"rtls").digest() != hashlib.new("sha256", b"rtls").digest():
            raise AssertionError("hashlib and _hashlib disagree")
        if not hasattr(_hashlib, "pbkdf2_hmac"):
            raise AssertionError("retained _hashlib lost pbkdf2_hmac")
        if "python-build-cacert.pem" not in os.listdir(Path(ssl.__file__).parent):
            raise RuntimeError("test CA bundle is not beside the ssl facade")
        mode = "rtls"
        results["interpreter"] = sys.version.split()[0]
        results["ssl_backend"] = getattr(ssl, "__version__", "unknown")
        results["ssl_extension_absent"] = True
        results["hashlib_retained"] = True
        results["ignore_environment"] = sys.flags.ignore_environment
        results["isolated_mode"] = sys.flags.isolated
        if not issubclass(ssl.SSLSocket, socket.socket):
            raise AssertionError("RTLS SSLSocket is not a socket.socket subtype")

    root = certdata / "capath" / "ceff1710.0"
    untrusted_root = certdata / "leaf-missing-aki.ca.pem"
    outcomes: dict[str, str] = {}
    outcomes["valid_tls13"] = tls_exchange(
        ssl, certdata / "keycert3.pem", root
    )
    outcomes["wrong_hostname"] = tls_exchange(
        ssl, certdata / "keycert3.pem", root, hostname="wrong.invalid"
    )
    outcomes["untrusted_issuer"] = tls_exchange(
        ssl, certdata / "keycert3.pem", untrusted_root
    )

    with tempfile.TemporaryDirectory(prefix="rtls-contract-") as temporary:
        work = Path(temporary)
        expired_cert, expired_key = make_expired_certificate(certdata, work / "expired")
        outcomes["expired_leaf"] = tls_exchange(
            ssl,
            expired_cert,
            certdata / "pycacert.pem",
            keyfile=expired_key,
        )
        outcomes["strict_missing_aki"] = tls_exchange(
            ssl,
            certdata / "leaf-missing-aki.keycert.pem",
            certdata / "leaf-missing-aki.ca.pem",
            hostname="example.com",
        )
        outcomes["malformed_certificate_chain"] = load_malformed_chain(
            ssl, certdata, work
        )

    if mode == "rtls":
        trust_cases = {
            "default_bundle": {
                "SSL_CERT_FILE": None,
                "SSL_CERT_DIR": None,
                "PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE": None,
            },
            "explicit_file": {
                "SSL_CERT_FILE": str(root),
                "SSL_CERT_DIR": None,
                "PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE": None,
            },
            "hashed_directory": {
                "SSL_CERT_FILE": None,
                "SSL_CERT_DIR": str(certdata / "capath"),
                "PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE": None,
            },
            "empty_file_override": {
                "SSL_CERT_FILE": "",
                "SSL_CERT_DIR": None,
                "PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE": None,
            },
            "invalid_file_override": {
                "SSL_CERT_FILE": str(certdata / "missing-ca.pem"),
                "SSL_CERT_DIR": None,
                "PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE": None,
            },
            "empty_directory_override": {
                "SSL_CERT_FILE": None,
                "SSL_CERT_DIR": "",
                "PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE": None,
            },
            "invalid_directory_override": {
                "SSL_CERT_FILE": None,
                "SSL_CERT_DIR": str(certdata / "missing-capath"),
                "PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE": None,
            },
            "fallback_opt_out": {
                "SSL_CERT_FILE": None,
                "SSL_CERT_DIR": None,
                "PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE": "1",
            },
        }
        for name, overrides in trust_cases.items():
            with environment(overrides):
                outcomes[name] = tls_exchange(
                    ssl,
                    certdata / "keycert3.pem",
                    None,
                    client_context_factory=lambda: ssl.create_default_context(),
                )

    outcomes["default_https"] = https_default_context(ssl, certdata, mode)
    asyncio.run(asyncio_default_context(ssl, certdata, mode))
    outcomes["default_asyncio_tls"] = "passed"
    results["certificate_and_runtime_cases"] = outcomes

    expected = {
        "valid_tls13": "accepted",
        "wrong_hostname": "rejected",
        "untrusted_issuer": "rejected",
        "expired_leaf": "rejected",
        "strict_missing_aki": "rejected",
        "malformed_certificate_chain": "rejected",
        "default_https": "passed",
        "default_asyncio_tls": "passed",
    }
    if mode == "rtls":
        expected.update(
            {
                "default_bundle": "accepted",
                "explicit_file": "accepted",
                "hashed_directory": "accepted",
                "empty_file_override": "rejected",
                "invalid_file_override": "rejected",
                "empty_directory_override": "rejected",
                "invalid_directory_override": "rejected",
                "fallback_opt_out": "rejected",
            }
        )
    for name, prefix in expected.items():
        if not str(outcomes[name]).startswith(prefix):
            failures.append(name)

    results["contract_result"] = "blocked" if failures else "passed"
    results["blocking_cases"] = failures
    print(json.dumps(results, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
