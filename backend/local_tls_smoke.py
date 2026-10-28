import socket
import ssl as stdlib_ssl
import sys
import threading
from pathlib import Path

checkout = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(checkout / "src"))

import rtls as ssl

certdata = checkout / "tests" / "certdata"
root_cert = certdata / "root_cert.pem"
leaf_chain = certdata / "leaf_chain.pem"
leaf_key = certdata / "leaf_key.pem"


def tls_context(module, server_side):
    protocol = module.PROTOCOL_TLS_SERVER if server_side else module.PROTOCOL_TLS_CLIENT
    context = module.SSLContext(protocol)
    context.minimum_version = module.TLSVersion.TLSv1_3
    context.maximum_version = module.TLSVersion.TLSv1_3
    if server_side:
        context.load_cert_chain(str(leaf_chain), str(leaf_key))
    else:
        context.check_hostname = True
        context.verify_mode = module.CERT_REQUIRED
        context.load_verify_locations(cafile=str(root_cert))
    return context


def exchange(server_module, label):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(5)
    errors = []

    def serve():
        try:
            raw, _ = listener.accept()
            raw.settimeout(5)
            with server_context.wrap_socket(raw, server_side=True) as tls:
                if tls.recv(4) != b"ping":
                    raise AssertionError("server received an unexpected payload")
                tls.sendall(b"pong")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            listener.close()

    server_context = tls_context(server_module, True)
    thread = threading.Thread(target=serve)
    thread.start()
    client_context = tls_context(ssl, False)
    try:
        with socket.create_connection(listener.getsockname(), timeout=5) as raw, client_context.wrap_socket(raw, server_hostname="localhost") as tls:
            tls.sendall(b"ping")
            if tls.recv(4) != b"pong":
                raise AssertionError("client received an unexpected payload")
            if tls.version() != "TLSv1.3":
                raise AssertionError(f"unexpected negotiated version: {tls.version()}")
            if not tls.getpeercert():
                raise AssertionError("client did not receive a verified peer certificate")
    finally:
        thread.join(5)
    if thread.is_alive():
        raise TimeoutError(f"{label} TLS server did not finish")
    if errors:
        raise errors[0]
    print(f"passed: Graviola client with {label} server, verified TLS 1.3")


if ssl._rustls.crypto_provider() != "rustls-graviola":
    raise AssertionError("RTLS is not using the Graviola provider")
if ssl._rustls.graviola_version() != "0.4.1":
    raise AssertionError("unexpected Graviola version")

exchange(ssl, "Graviola")
exchange(stdlib_ssl, "CPython OpenSSL")
