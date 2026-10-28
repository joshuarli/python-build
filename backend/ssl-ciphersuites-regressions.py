from __future__ import annotations

import socket
import ssl
import sysconfig
import unittest
from pathlib import Path

from test.test_ssl import HOST, ThreadedEchoServer

TLS13_AES128 = "TLS_AES_128_GCM_SHA256"
TLS13_AES256 = "TLS_AES_256_GCM_SHA384"
TLS13_CHACHA = "TLS_CHACHA20_POLY1305_SHA256"
CERTIFICATE = (
    Path(sysconfig.get_path("stdlib")) / "test" / "certdata" / "keycert3.pem"
)


def _context(server_side: bool, version: ssl.TLSVersion) -> ssl.SSLContext:
    protocol = ssl.PROTOCOL_TLS_SERVER if server_side else ssl.PROTOCOL_TLS_CLIENT
    context = ssl.SSLContext(protocol)
    context.minimum_version = version
    context.maximum_version = version
    if server_side:
        context.load_cert_chain(str(CERTIFICATE))
    else:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


def _negotiate(client_context: ssl.SSLContext, server_context: ssl.SSLContext):
    server = ThreadedEchoServer(context=server_context, chatty=False)
    with server, client_context.wrap_socket(socket.socket()) as connection:
        try:
            connection.connect((HOST, server.port))
        except ssl.SSLError as error:
            return error
        return connection.cipher()


class CipherSuiteControlTests(unittest.TestCase):
    def test_tls13_selection_is_independent_and_atomic(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        tls12_before = [
            cipher["name"]
            for cipher in context.get_ciphers()
            if cipher["protocol"] == "TLSv1.2"
        ]

        context.set_ciphersuites(f"{TLS13_CHACHA}:unsupported:{TLS13_AES256}")
        tls13 = [
            cipher["name"]
            for cipher in context.get_ciphers()
            if cipher["protocol"] == "TLSv1.3"
        ]
        self.assertEqual(tls13, [TLS13_CHACHA, TLS13_AES256])
        self.assertEqual(
            [
                cipher["name"]
                for cipher in context.get_ciphers()
                if cipher["protocol"] == "TLSv1.2"
            ],
            tls12_before,
        )

        context.set_ciphersuites(f"{TLS13_AES128}:{TLS13_AES128}")
        self.assertEqual(
            [
                cipher["name"]
                for cipher in context.get_ciphers()
                if cipher["protocol"] == "TLSv1.3"
            ],
            [TLS13_AES128, TLS13_AES128],
        )

        context.set_ciphersuites(f"{TLS13_CHACHA}:{TLS13_AES256}")

        context.set_ciphers("AES128")
        self.assertEqual(
            [
                cipher["name"]
                for cipher in context.get_ciphers()
                if cipher["protocol"] == "TLSv1.3"
            ],
            tls13,
        )

        before_failure = [cipher["name"] for cipher in context.get_ciphers()]
        with self.assertRaises(ssl.SSLError) as caught:
            context.set_ciphersuites("unsupported")
        self.assertEqual(caught.exception.errno, 0)
        self.assertIn("No cipher suite can be selected", str(caught.exception))
        self.assertEqual(
            [cipher["name"] for cipher in context.get_ciphers()], before_failure
        )

        context.set_ciphersuites("")
        self.assertEqual(
            [
                cipher["name"]
                for cipher in context.get_ciphers()
                if cipher["protocol"] == "TLSv1.3"
            ],
            [],
        )

    def test_ciphersuites_argument_contract(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        for value, name in ((None, "None"), (1, "int"), (b"x", "bytes")):
            with self.subTest(type=name), self.assertRaises(TypeError) as caught:
                context.set_ciphersuites(value)
            self.assertEqual(
                caught.exception.args,
                (f"set_ciphersuites() argument must be str, not {name}",),
            )
        with self.assertRaises(ValueError) as caught:
            context.set_ciphersuites(f"{TLS13_AES128}\0{TLS13_AES256}")
        self.assertEqual(caught.exception.args, ("embedded null character",))

    def test_tls12_negotiation_ignores_tls13_selection(self):
        server_context = _context(True, ssl.TLSVersion.TLSv1_2)
        client_context = _context(False, ssl.TLSVersion.TLSv1_2)
        server_context.set_ciphers("AES128")
        client_context.set_ciphers("AES128")
        server_context.set_ciphersuites(TLS13_AES128)
        client_context.set_ciphersuites(TLS13_AES256)
        negotiated = _negotiate(client_context, server_context)
        self.assertIsInstance(negotiated, tuple)
        self.assertEqual(negotiated[1], "TLSv1.2")

        client_context.set_ciphers("AES256")
        mismatch = _negotiate(client_context, server_context)
        self.assertIsInstance(mismatch, ssl.SSLError)

    def test_tls13_negotiation_ignores_tls12_selection(self):
        server_context = _context(True, ssl.TLSVersion.TLSv1_3)
        client_context = _context(False, ssl.TLSVersion.TLSv1_3)
        server_context.set_ciphers("AES128")
        client_context.set_ciphers("AES256")
        server_context.set_ciphersuites(TLS13_AES128)
        client_context.set_ciphersuites(TLS13_AES128)
        negotiated = _negotiate(client_context, server_context)
        self.assertIsInstance(negotiated, tuple)
        self.assertEqual(negotiated[0], TLS13_AES128)

        client_context.set_ciphersuites(TLS13_AES256)
        mismatch = _negotiate(client_context, server_context)
        self.assertIsInstance(mismatch, ssl.SSLError)


if __name__ == "__main__":
    unittest.main(verbosity=2)
