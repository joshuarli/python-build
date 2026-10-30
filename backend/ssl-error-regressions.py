from __future__ import annotations

import socket
import sysconfig
import threading
import unittest
from pathlib import Path

import rtls as ssl
from rtls import _rustls

CERTDATA = Path(sysconfig.get_path("stdlib")) / "test" / "certdata"
SERVER_CERT = CERTDATA / "keycert3.pem"
CLIENT_CA = CERTDATA / "pycacert.pem"


def _hostname_mismatch_alert():
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(str(SERVER_CERT))
    client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client_context.load_verify_locations(str(CLIENT_CA))

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(5)
    server_result = []

    def serve() -> None:
        connection, _ = listener.accept()
        try:
            with server_context.wrap_socket(connection, server_side=True):
                server_result.append(None)
        except Exception as error:  # noqa: BLE001
            server_result.append(error)
        finally:
            listener.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        connection = socket.create_connection(listener.getsockname(), timeout=5)
        try:
            with client_context.wrap_socket(
                connection, server_hostname="127.0.0.1"
            ):
                client_error = None
        except Exception as error:  # noqa: BLE001
            client_error = error
    finally:
        thread.join(5)
    if thread.is_alive():
        raise RuntimeError("TLS error regression handshake did not finish")
    return client_error, server_result[0]


def _no_shared_cipher():
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.minimum_version = ssl.TLSVersion.TLSv1_2
    server_context.maximum_version = ssl.TLSVersion.TLSv1_2
    server_context.load_cert_chain(str(SERVER_CERT))
    server_context.set_ciphers("AES256")
    client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client_context.check_hostname = False
    client_context.verify_mode = ssl.CERT_NONE
    client_context.minimum_version = ssl.TLSVersion.TLSv1_2
    client_context.maximum_version = ssl.TLSVersion.TLSv1_2
    client_context.set_ciphers("AES128")

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(5)
    server_result = []

    def serve() -> None:
        connection, _ = listener.accept()
        try:
            with server_context.wrap_socket(connection, server_side=True):
                server_result.append(None)
        except Exception as error:  # noqa: BLE001
            server_result.append(error)
        finally:
            listener.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        connection = socket.create_connection(listener.getsockname(), timeout=5)
        try:
            with client_context.wrap_socket(
                connection, server_hostname="localhost"
            ):
                client_error = None
        except Exception as error:  # noqa: BLE001
            client_error = error
    finally:
        thread.join(5)
    if thread.is_alive():
        raise RuntimeError("no-shared-cipher handshake did not finish")
    return client_error, server_result[0]


class SSLErrorRegressionTests(unittest.TestCase):
    def test_empty_capath_error_preserves_x509_code_and_reason(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        with self.assertRaises(ssl.SSLError) as caught:
            context.load_verify_locations(capath="")
        error = caught.exception
        self.assertEqual(error.errno, 113)
        self.assertEqual(error.library, "X509")
        self.assertEqual(error.reason, "INVALID_DIRECTORY")
        self.assertIn("[X509: INVALID_DIRECTORY]", str(error))

    def test_manual_exception_construction_matches_cpython(self):
        cases = (
            (ssl.SSLError, 1),
            (ssl.SSLWantReadError, 2),
            (ssl.SSLWantWriteError, 3),
            (ssl.SSLZeroReturnError, 6),
            (ssl.SSLEOFError, 8),
            (ssl.SSLCertVerificationError, 1),
        )
        for exception_type, code in cases:
            with self.subTest(exception_type=exception_type.__name__):
                error = exception_type(code, "message")
                self.assertEqual(error.args, (code, "message"))
                self.assertEqual(error.errno, code)
                self.assertEqual(str(error), "message")
                self.assertIsNone(error.library)
                self.assertIsNone(error.reason)
        verification_error = ssl.SSLCertVerificationError(1, "message")
        self.assertIsNone(getattr(verification_error, "verify_code", None))
        self.assertIsNone(getattr(verification_error, "verify_message", None))
        generated_verification_error = ssl.SSLCertVerificationError(
            "invalid certificate",
            verify_code=20,
            verify_message="unable to get local issuer certificate",
        )
        self.assertEqual(
            generated_verification_error.args[0], ssl.SSL_ERROR_SSL
        )
        self.assertEqual(generated_verification_error.errno, ssl.SSL_ERROR_SSL)
        self.assertEqual(generated_verification_error.verify_code, 20)
        self.assertEqual(
            generated_verification_error.verify_message,
            "unable to get local issuer certificate",
        )

    def test_rust_errors_use_numeric_ssl_codes(self):
        builder = _rustls.RustlsConfigBuilder()
        with self.assertRaises(ssl.SSLError) as caught:
            builder.set_groups("not-a-supported-group")
        self.assertEqual(caught.exception.args[0], ssl.SSL_ERROR_SSL)
        self.assertEqual(caught.exception.errno, ssl.SSL_ERROR_SSL)
        self.assertIsInstance(caught.exception.args[1], str)

    def test_peer_alert_has_cpython_reason_and_code(self):
        client_error, server_error = _hostname_mismatch_alert()
        self.assertIsInstance(client_error, ssl.SSLCertVerificationError)
        self.assertEqual(client_error.args[0], ssl.SSL_ERROR_SSL)
        self.assertEqual(client_error.verify_code, 62)
        self.assertIsInstance(server_error, ssl.SSLError)
        self.assertEqual(server_error.args[0], ssl.SSL_ERROR_SSL)
        self.assertIn("SSLV3_ALERT_BAD_CERTIFICATE", server_error.args[1])
        self.assertEqual(server_error.reason, "SSLV3_ALERT_BAD_CERTIFICATE")

    def test_no_shared_cipher_has_cpython_reason(self):
        client_error, server_error = _no_shared_cipher()
        self.assertIsInstance(client_error, ssl.SSLError)
        self.assertEqual(client_error.args[0], ssl.SSL_ERROR_SSL)
        self.assertEqual(
            client_error.reason, "SSLV3_ALERT_HANDSHAKE_FAILURE"
        )
        self.assertIsInstance(server_error, ssl.SSLError)
        self.assertEqual(server_error.args[0], ssl.SSL_ERROR_SSL)
        self.assertIn("NO_SHARED_CIPHER", server_error.args[1])
        self.assertEqual(server_error.reason, "NO_SHARED_CIPHER")


if __name__ == "__main__":
    unittest.main(verbosity=2)
