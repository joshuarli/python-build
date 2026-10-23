from __future__ import annotations

import ssl
import sys
import tempfile
import unittest
from pathlib import Path


NULLBYTE_CERTIFICATE = Path(sys.argv.pop(1)).resolve()


class SSLUtilitiesContract(unittest.TestCase):
    def test_no_openssl_api_version_sentinel(self):
        if ssl.OPENSSL_VERSION.startswith("OpenSSL "):
            self.skipTest("the reference backend uses OpenSSL")
        self.assertEqual(ssl._OPENSSL_API_VERSION, (0, 0, 0, 0, 0))
        self.assertEqual(ssl._ssl._OPENSSL_API_VERSION, (0, 0, 0, 0, 0))

    def test_rand_bytes_rejects_negative_length(self):
        with self.assertRaisesRegex(ValueError, "num must be positive"):
            ssl.RAND_bytes(-5)

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
