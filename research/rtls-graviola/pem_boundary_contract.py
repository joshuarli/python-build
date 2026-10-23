from __future__ import annotations

import re
import ssl
import sys
import tempfile
import unittest
from pathlib import Path

CERTDATA = Path(sys.argv.pop(1)).resolve()


class PEMBoundaryContract(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.chain = CERTDATA / "keycert3.pem"
        self.ca = (CERTDATA / "pycacert.pem").read_text()

    def write(self, name, contents):
        path = self.root / name
        path.write_bytes(contents)
        return path

    def test_certificate_footer_suffix_in_cadata_is_atomic(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cadata=self.ca)
        before = context.cert_store_stats()
        malformed = self.ca.replace("-----END CERTIFICATE-----", "-----END CERTIFICATE-----junk")
        with self.assertRaises(ssl.SSLError):
            context.load_verify_locations(cadata=malformed)
        self.assertEqual(context.cert_store_stats(), before)

    def test_certificate_footer_suffix_in_cafile(self):
        malformed = self.ca.replace("-----END CERTIFICATE-----", "-----END CERTIFICATE-----junk")
        path = self.write("malformed-ca.pem", malformed.encode())
        with self.assertRaises(ssl.SSLError):
            ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).load_verify_locations(cafile=path)

    def test_crl_footer_suffix_in_cafile(self):
        contents = (CERTDATA / "revocation.crl").read_bytes()
        malformed = contents.replace(b"-----END X509 CRL-----", b"-----END X509 CRL-----junk")
        self.assertNotEqual(malformed, contents)
        path = self.write("malformed-crl.pem", malformed)
        with self.assertRaises(ssl.SSLError):
            ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).load_verify_locations(cafile=path)

    def test_certificate_footer_suffix_in_chain(self):
        contents = self.chain.read_bytes().replace(
            b"-----END CERTIFICATE-----", b"-----END CERTIFICATE-----junk"
        )
        path = self.write("malformed-chain.pem", contents)
        with self.assertRaises(ssl.SSLError):
            ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(path)

    def test_private_key_footer_suffix(self):
        contents, count = re.subn(
            rb"(-----END (?:(?:RSA|EC|ENCRYPTED) )?PRIVATE KEY-----)",
            rb"\1junk",
            self.chain.read_bytes(),
        )
        self.assertEqual(count, 1)
        path = self.write("malformed-key.pem", contents)
        with self.assertRaises(ssl.SSLError):
            ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(self.chain, path)

    def test_key_format_words_in_surrounding_text(self):
        path = self.write("key-comment.pem", b"info ENCRYPTED PRIVATE KEY\n" + self.chain.read_bytes())
        ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(self.chain, path)

    def test_first_private_key_is_selected(self):
        contents = self.chain.read_bytes() + (
            b"\n-----BEGIN ENCRYPTED PRIVATE KEY-----\nbroken\n-----END ENCRYPTED PRIVATE KEY-----\n"
        )
        path = self.write("unused-key.pem", contents)
        ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(self.chain, path)

    def test_password_callback_uses_selected_key_only(self):
        protected = (CERTDATA / "keycert.passwd.pem").read_bytes()
        key_start = protected.find(b"-----BEGIN ENCRYPTED PRIVATE KEY-----")
        self.assertGreaterEqual(key_start, 0)
        encrypted_key = protected[key_start:]
        calls = []

        def unexpected_password():
            calls.append(True)
            raise AssertionError("the selected private key is unencrypted")

        cases = (
            self.chain.read_bytes() + b"\n" + encrypted_key,
            b"ENCRYPTED PRIVATE KEY\n" + self.chain.read_bytes(),
        )
        for index, contents in enumerate(cases):
            with self.subTest(index=index):
                path = self.write(f"selected-key-{index}.pem", contents)
                ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(
                    path,
                    password=unexpected_password,
                )
                self.assertEqual(calls, [])

    def test_invalid_certificate_precedes_password_callback(self):
        protected = (CERTDATA / "keycert.passwd.pem").read_bytes()
        key_start = protected.find(b"-----BEGIN ENCRYPTED PRIVATE KEY-----")
        self.assertGreaterEqual(key_start, 0)
        contents = (
            b"-----BEGIN CERTIFICATE-----\n@@@\n-----END CERTIFICATE-----\n"
            + protected[key_start:]
        )
        path = self.write("invalid-cert-encrypted-key.pem", contents)
        calls = []

        def password():
            calls.append(True)
            return "somepass"

        with self.assertRaises(ssl.SSLError):
            ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(
                path,
                password=password,
            )
        self.assertEqual(calls, [])

    def test_footer_whitespace_and_surrounding_text(self):
        for suffix in (" \t", "\v", "\f"):
            with self.subTest(suffix=suffix):
                contents = "surrounding text\n" + self.ca.replace(
                    "-----END CERTIFICATE-----", "-----END CERTIFICATE-----" + suffix
                ) + "surrounding text\n"
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                context.load_verify_locations(cadata=contents)
                self.assertEqual(context.cert_store_stats()["x509"], 1)


if __name__ == "__main__":
    unittest.main()
