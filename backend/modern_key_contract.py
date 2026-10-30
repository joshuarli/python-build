from __future__ import annotations

import argparse
import base64
import ssl
import subprocess
import tempfile
import unittest
from pathlib import Path
from runpy import run_path

_fixtures = run_path(str(Path(__file__).with_name("certificate_contract.py")))
der_children = _fixtures["der_children"]
der_value = _fixtures["der_value"]


class ModernKeys(unittest.TestCase):
    def load(self, key, password=b"fixture-password", certificate=None):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate or self.cert, key, password=password)
        return context

    def peer_certificate(self, server, certificate=None):
        certificates = []
        for version in (ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3):
            server.minimum_version = version
            server.maximum_version = version
            certificates.append(self.version_peer_certificate(server, version, certificate))
        self.assertEqual(certificates[0], certificates[1])
        return certificates[0]

    def version_peer_certificate(self, server, version, certificate):
        client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        client.minimum_version = version
        client.maximum_version = version
        client.load_verify_locations(certificate or self.cert)
        ci, co, si, so = (ssl.MemoryBIO() for _ in range(4))
        c = client.wrap_bio(ci, co, server_hostname="localhost")
        s = server.wrap_bio(si, so, server_side=True)
        complete = set()
        for _ in range(100):
            for name, connection in (("client", c), ("server", s)):
                if name not in complete:
                    try:
                        connection.do_handshake()
                        complete.add(name)
                    except ssl.SSLWantReadError:
                        pass
            if co.pending:
                si.write(co.read())
            if so.pending:
                ci.write(so.read())
            if len(complete) == 2:
                self.assertIn(c.version(), ("TLSv1.2", "TLSv1.3"))
                return c.getpeercert(True)
        self.fail("TLS handshake did not finish")

    def test_modern_formats(self):
        for name, key in self.modern.items():
            with self.subTest(name=name):
                context = self.load(key)
                self.assertEqual(self.peer_certificate(context), self.expected_cert)
        self.load(self.ec_key, certificate=self.ec_cert)

    def test_cpython_encrypted_fixture(self):
        certificate = self.certdata / "ssl_cert.pem"
        server = self.load(self.certdata / "ssl_key.passwd.pem", "somepass", certificate)
        expected = ssl.PEM_cert_to_DER_cert(certificate.read_text())
        self.assertEqual(self.peer_certificate(server, certificate), expected)

    def test_password_callback(self):
        calls = []
        def password():
            calls.append(True)
            return "fixture-password"
        self.assertEqual(self.peer_certificate(self.load(self.modern["sha256-aes256"], password)), self.expected_cert)
        self.assertEqual(calls, [True])

    def test_rejected_loads_preserve_identity(self):
        cases = [(name, path, None if name.startswith("pbkdf2-") else b"fixture-password")
                 for name, path in self.retired.items()]
        cases += [("wrong-password", self.modern["sha256-aes256"], b"wrong"),
                  ("missing-password", self.modern["sha256-aes256"], None),
                  ("malformed-pem", self.malformed_pem, b"fixture-password"),
                  ("malformed-der", self.malformed_der, b"fixture-password"),
                  ("key-mismatch", self.ec_key, None)]
        for name, key, password in cases:
            with self.subTest(name=name):
                context = self.load(self.plain)
                if self.reference and name in self.retired:
                    if name.startswith(("scrypt-", "pbkdf2-")) or name == "traditional-des":
                        with self.assertRaises(ssl.SSLError):
                            context.load_cert_chain(self.cert, key, password=password)
                    else:
                        context.load_cert_chain(self.cert, key, password=password)
                    continue
                with self.assertRaises(ssl.SSLError) as caught:
                    context.load_cert_chain(self.cert, key, password=password)
                if name.startswith("scrypt-"):
                    self.assertIn("scrypt", str(caught.exception))
                if name.startswith("pbkdf2-"):
                    self.assertIn("PBKDF2 iteration count", str(caught.exception))
                self.assertEqual(self.peer_certificate(context), self.expected_cert)

    def test_callback_failure_preserves_identity(self):
        context = self.load(self.plain)
        marker = RuntimeError("password callback rejected")
        def password():
            raise marker
        with self.assertRaises(RuntimeError) as caught:
            context.load_cert_chain(self.cert, self.modern["sha256-aes256"], password=password)
        self.assertIs(caught.exception, marker)
        self.assertEqual(self.peer_certificate(context), self.expected_cert)

    def test_native_selected_key_query(self):
        if self.reference:
            self.skipTest("native query belongs to the experimental binding")
        context = self.load(self.plain)
        builder = context._builder
        cert = self.cert.read_bytes()
        plain = self.plain.read_bytes()
        encrypted = self.modern["sha256-aes256"].read_bytes()
        self.assertFalse(builder.cert_chain_key_is_encrypted(cert, plain + encrypted))
        self.assertTrue(builder.cert_chain_key_is_encrypted(cert, encrypted + plain))
        self.assertFalse(builder.cert_chain_key_is_encrypted(cert, b"ENCRYPTED PRIVATE KEY\n" + plain))
        with self.assertRaises(ssl.SSLError):
            builder.cert_chain_key_is_encrypted(b"invalid certificate", encrypted)


def generate(openssl, certdata, directory):
    def command(*arguments):
        result = subprocess.run([str(openssl), *map(str, arguments)], capture_output=True, check=False)
        if result.returncode:
            raise RuntimeError(f"fixture generation failed: {result.stderr.decode()}")
    def pkcs8(name, *options):
        path = directory / f"{name}.pem"
        command("pkcs8", "-topk8", "-in", certdata / "keycert.pem", "-out", path,
                "-passout", f"file:{password}", *options)
        return path
    password = directory / "password"
    password.write_text("fixture-password\n")
    ModernKeys.cert = directory / "certificate.pem"
    command("x509", "-in", certdata / "keycert.pem", "-out", ModernKeys.cert)
    ModernKeys.expected_cert = ssl.PEM_cert_to_DER_cert(ModernKeys.cert.read_text())
    ModernKeys.plain = pkcs8("plain-pkcs8", "-nocrypt")
    plain_rsa = directory / "plain-pkcs1.pem"
    command("rsa", "-traditional", "-in", certdata / "keycert.pem", "-out", plain_rsa)
    ModernKeys.ec_key = directory / "plain-sec1.pem"
    ModernKeys.ec_cert = directory / "ec-certificate.pem"
    command("ec", "-in", certdata / "keycertecc.pem", "-out", ModernKeys.ec_key)
    command("x509", "-in", certdata / "keycertecc.pem", "-out", ModernKeys.ec_cert)
    ModernKeys.modern = {"plaintext-pkcs8": ModernKeys.plain, "plaintext-pkcs1": plain_rsa}
    for bits in (128, 192, 256):
        for sha in (224, 256, 384, 512):
            name = f"sha{sha}-aes{bits}"
            ModernKeys.modern[name] = pkcs8(name, "-v2", f"aes-{bits}-cbc", "-v2prf", f"hmacWithSHA{sha}")
    ModernKeys.modern["scrypt-aes256"] = pkcs8("scrypt", "-scrypt", "-scrypt_N", "1024")
    ModernKeys.retired = {
        "pbes2-sha1": pkcs8("sha1", "-v2", "aes-256-cbc", "-v2prf", "hmacWithSHA1"),
        "pbes2-3des": pkcs8("3des", "-v2", "des3", "-v2prf", "hmacWithSHA256"),
        "pkcs12-pbes1": pkcs8("pbes1", "-v1", "PBE-SHA1-3DES"),
    }
    for cipher in ("aes128", "aes256", "des3", "des"):
        path = directory / f"traditional-{cipher}.pem"
        command("rsa", "-traditional", "-in", certdata / "keycert.pem", "-out", path,
                f"-{cipher}", "-passout", f"file:{password}", "-provider", "default", "-provider", "legacy")
        ModernKeys.retired[f"traditional-{cipher}"] = path
    for source, cases in (
        (ModernKeys.modern["scrypt-aes256"], (("scrypt-memory-limit", 32768),
         ("scrypt-overflow", 1 << 63), ("scrypt-zero", 0))),
        (ModernKeys.modern["sha256-aes256"], (("pbkdf2-zero", 0),
         ("pbkdf2-iteration-limit", 100_000_001))),
    ):
        pem = source.read_bytes()
        der = base64.b64decode(b"".join(pem.splitlines()[1:-1]))
        outer = der_children(der)
        algorithm = der_children(outer[0])
        parameters = der_children(algorithm[1])
        kdf = der_children(parameters[0])
        costs = der_children(kdf[1])
        for name, n in cases:
            integer = n.to_bytes(max(1, (n.bit_length() + 8) // 8), "big")
            changed_costs = costs[:1] + [der_value(2, integer)] + costs[2:]
            changed_kdf = der_value(0x30, kdf[0] + der_value(0x30, b"".join(changed_costs)))
            changed_algorithm = der_value(0x30, algorithm[0] + der_value(0x30, changed_kdf + parameters[1]))
            changed = der_value(0x30, changed_algorithm + outer[1])
            body = base64.b64encode(changed)
            rows = b"\n".join(body[offset:offset + 64] for offset in range(0, len(body), 64))
            path = directory / f"{name}.pem"
            path.write_bytes(b"-----BEGIN ENCRYPTED PRIVATE KEY-----\n" + rows + b"\n-----END ENCRYPTED PRIVATE KEY-----\n")
            ModernKeys.retired[name] = path
    ModernKeys.malformed_pem = directory / "malformed.pem"
    ModernKeys.malformed_pem.write_bytes(b"-----BEGIN ENCRYPTED PRIVATE KEY-----\n!invalid!\n-----END ENCRYPTED PRIVATE KEY-----\n")
    ModernKeys.malformed_der = directory / "malformed-der.pem"
    ModernKeys.malformed_der.write_bytes(b"-----BEGIN ENCRYPTED PRIVATE KEY-----\nMAMCAQE=\n-----END ENCRYPTED PRIVATE KEY-----\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--certdata", required=True, type=Path)
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--openssl", required=True, type=Path)
    parser.add_argument("--reference", action="store_true")
    args = parser.parse_args()
    args.workdir.mkdir(parents=True, exist_ok=True)
    ModernKeys.reference = args.reference
    ModernKeys.certdata = args.certdata
    with tempfile.TemporaryDirectory(dir=args.workdir, prefix="modern-keys-") as temporary:
        generate(args.openssl, args.certdata, Path(temporary))
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ModernKeys))
    return not result.wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(main())
