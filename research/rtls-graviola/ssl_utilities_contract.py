from __future__ import annotations

import ctypes
import ssl
import sys
import tempfile
import unittest
from pathlib import Path


NULLBYTE_CERTIFICATE = Path(sys.argv.pop(1)).resolve()
IPV6_SAN_CERTIFICATE = """-----BEGIN CERTIFICATE-----
MIIEuzCCAyOgAwIBAgIBATANBgkqhkiG9w0BAQsFADBNMQswCQYDVQQGEwJYWTEm
MCQGA1UECgwdUHl0aG9uIFNvZnR3YXJlIEZvdW5kYXRpb24gQ0ExFjAUBgNVBAMM
DW91ci1jYS1zZXJ2ZXIwIBcNMTgwODI5MTQyMzE2WhgPMjUyNTEwMjgxNDIzMTZa
MEwxCzAJBgNVBAYTAlhZMSMwIQYDVQQKDBpQeXRob24gU29mdHdhcmUgRm91bmRh
dGlvbjEYMBYGA1UEAwwPd3d3LmV4YW1wbGUub3JnMIIBojANBgkqhkiG9w0BAQEF
AAOCAY8AMIIBigKCAYEAmBGPpSMEv8PoAFOT38Uni+KjBeU7RZK4ny9KEGgo1hW/
I3l9kW9bSmjm8q2Jk1EVVmzJCNSyTkFmLRpQDaNpr3+FQ9cGWf8f05spcXtwO4rU
k2YGbhlyx7RT/cJO8kuOgZVXDat2aDou5JPDcU4lKoLJi4NzY/iH5PDiO3NQXD9q
WtcGTv5dz01qrRUi7BRLziuTemT6iCwFIubxJDohXn8VRx7w+DdyFkhYEsIg4vSo
Z7XUcGvmsbGcY6v6O9BY0DuauULspvWg6qqOOzzMpBG9YHUwUCtZj5YjCrC4uc8n
CP8qZtTxHB+d/vfxflNgdW5rwP/TwcfE+4VMnJQW0BwpnXFyGAoBa+QGxkt4xXlT
4he4Qj49ZP43KWsl2QLVpqiU5ZFyhmzOvAIDPwxztHxgmBkVMNr4Vd2SEQptAasH
6K3hYftqDMmYw476P7mY2TWs3aXMLzstHJRZDkcFSNM0yIsV2EleMTdQV/NtSQro
WLm66PPZvjEo8TteKoLNAgMBAAGjgaQwgaEwDAYDVR0TAQH/BAIwADAOBgNVHQ8B
Af8EBAMCBaAwEwYDVR0lBAwwCgYIKwYBBQUHAwEwHQYDVR0OBBYEFHMNTh9K7PJT
D1P8hW/Pgs2j6BGNMB8GA1UdIwQYMBaAFMAKKyhD3l/JfUflR5s28mWMZzviMCwG
A1UdEQQlMCOCD3d3dy5leGFtcGxlLm9yZ4cQIAENuAAAAAAAAAAAAAAAATANBgkq
hkiG9w0BAQsFAAOCAYEAMC43N7pS9DfgctXHgjJk/Yw9sqOdwUqZmXvq0Y4u917x
wd2USO+LDcgW1TgK3bgZpr8ki9Dm1363i4RAIiKslSOP+koY5eIPKJ4FTo6p/nIJ
RR50LLwjK/L/83FWezZleFUQ8kg0PNdARMir1JVI9tQqh7p3S0DHNZ1VjGiwvKXQ
2gIMUQ736lFY9gGCfb83A9svzVFfpaEL1KZ+MDzydhG4in2itwQD43Gi4XPFcAtG
KScaoZClMCOOP2r6KuZoWL9Mv9Q73n/13sXLmmmhmvqwVx7HwsVNN40qzOwFyyvZ
5ThAuoVryk1KQ8m8FTd7QJKaFj+508yPZdlB2RV1egZ7ItO0IHzttA9+ptdqZ3lc
W7QCiWloQmeDWB8wvG5hKqKvfd6ABICy0GbKK8jcoB6IwBN4MFXKJjfO6brDqWiw
lcKnJTUPBxaBv8x/A0r1fWuo6f8ZmMAWcoCvkK4zwq8e/7UY2LCdz1N9N1ZOn2UW
v10Q1MAQxXRsA8Ycixsd
-----END CERTIFICATE-----
"""


class IndexOnly:
    def __index__(self):
        return 2


class BadIndex:
    def __index__(self):
        return 1.5


class SSLUtilitiesContract(unittest.TestCase):
    def test_no_openssl_api_version_sentinel(self):
        if ssl.OPENSSL_VERSION.startswith("OpenSSL "):
            self.skipTest("the reference backend uses OpenSSL")
        self.assertEqual(ssl._OPENSSL_API_VERSION, (0, 0, 0, 0, 0))
        self.assertEqual(ssl._ssl._OPENSSL_API_VERSION, (0, 0, 0, 0, 0))

    def test_rand_bytes_argument_conversion(self):
        self.assertEqual(ssl.RAND_bytes(False), b"")
        self.assertEqual(len(ssl.RAND_bytes(True)), 1)
        self.assertEqual(len(ssl.RAND_bytes(IndexOnly())), 2)
        with self.assertRaisesRegex(TypeError, "cannot be interpreted as an integer"):
            ssl.RAND_bytes(1.0)
        with self.assertRaisesRegex(TypeError, r"__index__\(\) must return an int"):
            ssl.RAND_bytes(BadIndex())
        with self.assertRaisesRegex(ValueError, "num must be positive"):
            ssl.RAND_bytes(-5)
        int_bits = 8 * ctypes.sizeof(ctypes.c_int)
        int_min = -(1 << (int_bits - 1))
        int_max = (1 << (int_bits - 1)) - 1
        with self.assertRaisesRegex(ValueError, "num must be positive"):
            ssl.RAND_bytes(int_min)
        for value in (int_min - 1, int_max + 1, 1 << 1000):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    OverflowError, "Python int too large to convert to C int"
                ):
                    ssl.RAND_bytes(value)

    def test_rand_add_support_is_explicit(self):
        if ssl.OPENSSL_VERSION.startswith("OpenSSL "):
            self.assertIsNone(ssl.RAND_add("seed", 1.0))
        else:
            with self.assertRaisesRegex(
                NotImplementedError, "RAND_add entropy injection is unsupported"
            ):
                ssl.RAND_add("seed", 1.0)

    def test_protocol_names(self):
        self.assertEqual(ssl.get_protocol_name(ssl.PROTOCOL_TLS), "PROTOCOL_TLS")
        self.assertEqual(
            ssl.get_protocol_name(ssl.PROTOCOL_TLS_CLIENT), "PROTOCOL_TLS_CLIENT"
        )
        self.assertEqual(
            ssl.get_protocol_name(ssl.PROTOCOL_TLS_SERVER), "PROTOCOL_TLS_SERVER"
        )
        self.assertEqual(ssl.get_protocol_name(999999), "<unknown>")

    def test_cve_2013_4238_certificate_fields(self):
        certificate = ssl._ssl._test_decode_cert(str(NULLBYTE_CERTIFICATE))
        common_name = next(
            value
            for relative_name in certificate["subject"]
            for name, value in relative_name
            if name == "commonName"
        )
        self.assertEqual(common_name, "null.python.org\x00example.org")
        self.assertEqual(certificate["issuer"], certificate["subject"])
        self.assertEqual(
            certificate["subjectAltName"],
            (
                ("DNS", "altnull.python.org\x00example.com"),
                ("email", "null@python.org\x00user@example.org"),
                ("URI", "http://null.python.org\x00http://example.org"),
                ("IP Address", "192.0.2.1"),
                ("IP Address", "2001:DB8:0:0:0:0:0:1"),
            ),
        )

    def test_sslobject_peer_ipv6_san_case(self):
        certdata = NULLBYTE_CERTIFICATE.parent
        with tempfile.NamedTemporaryFile("w", suffix=".pem") as certfile:
            certfile.write(IPV6_SAN_CERTIFICATE)
            certfile.flush()
            server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            server_context.load_cert_chain(
                certfile.name, keyfile=str(certdata / "allsans.pem")
            )
            client_context = ssl.create_default_context(
                cafile=str(certdata / "pycacert.pem")
            )
            client_in = ssl.MemoryBIO()
            client_out = ssl.MemoryBIO()
            server_in = ssl.MemoryBIO()
            server_out = ssl.MemoryBIO()
            client = client_context.wrap_bio(
                client_in, client_out, server_hostname="www.example.org"
            )
            server = server_context.wrap_bio(
                server_in, server_out, server_side=True
            )
            client_done = False
            server_done = False
            for _ in range(10):
                if not client_done:
                    try:
                        client.do_handshake()
                        client_done = True
                    except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
                        pass
                if client_out.pending:
                    server_in.write(client_out.read())
                if not server_done:
                    try:
                        server.do_handshake()
                        server_done = True
                    except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
                        pass
                if server_out.pending:
                    client_in.write(server_out.read())
                if client_done and server_done:
                    break
            else:
                self.fail("TLS handshake did not finish")

        self.assertIn(
            ("IP Address", "2001:DB8:0:0:0:0:0:1"),
            client.getpeercert()["subjectAltName"],
        )

    def test_malformed_certificate_errors(self):
        malformed_certificates = {
            "non_pem": b"not a certificate\n",
            "bad_base64": (
                b"-----BEGIN CERTIFICATE-----\n!\n"
                b"-----END CERTIFICATE-----\n"
            ),
            "truncated_der": (
                b"-----BEGIN CERTIFICATE-----\nAA==\n"
                b"-----END CERTIFICATE-----\n"
            ),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, contents in malformed_certificates.items():
                with self.subTest(name=name):
                    path = root / f"{name}.pem"
                    path.write_bytes(contents)
                    with self.assertRaises(ssl.SSLError) as raised:
                        ssl._ssl._test_decode_cert(str(path))
                    self.assertEqual(
                        raised.exception.args,
                        ("Error decoding PEM-encoded file",),
                    )
            with self.assertRaises(ssl.SSLError) as raised:
                ssl._ssl._test_decode_cert(str(root / "missing.pem"))
            self.assertEqual(raised.exception.args, ("Can't open file",))


if __name__ == "__main__":
    unittest.main(verbosity=2)
