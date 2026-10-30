import json
import os
import ssl
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

CERTDATA = Path(sys.argv.pop(1)).resolve()


class SSLFactoryContract(unittest.TestCase):
    def test_factories_follow_keylog_environment_and_startup_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            for flags in ((), ("-E",), ("-I",)):
                with self.subTest(flags=flags):
                    path = str(Path(directory) / ("keylog" + str(len(flags))))
                    environment = os.environ.copy()
                    environment["SSLKEYLOGFILE"] = path
                    result = subprocess.run(
                        [sys.executable, *flags, "-B", "-c",
                         ("import json, ssl; print(json.dumps([factory().keylog_filename "
                         "for factory in (ssl.create_default_context, ssl._create_stdlib_context)]))")],
                        env=environment, text=True, capture_output=True, check=True,
                    )
                    self.assertEqual(json.loads(result.stdout), [None, None] if flags else [path, path])

    def test_unverified_factory_requires_certificate_with_private_key(self):
        with self.assertRaisesRegex(ValueError, "certfile must be specified"):
            ssl._create_unverified_context(keyfile="missing-private-key.pem")

    def test_unverified_factory_loads_default_authorities_when_verifying(self):
        with patch.dict(os.environ, {}, clear=False):
            for name in ("SSL_CERT_FILE", "SSL_CERT_DIR", "PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE"):
                os.environ.pop(name, None)
            os.environ["SSL_CERT_FILE"] = str(CERTDATA / "pycacert.pem")
            context = ssl._create_unverified_context(cert_reqs=ssl.CERT_REQUIRED)
            self.assertGreater(context.cert_store_stats()["x509_ca"], 0)
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            self.assertFalse(context.check_hostname)
            unverified = ssl._create_unverified_context()
            self.assertEqual(unverified.cert_store_stats()["x509_ca"], 0)
            self.assertEqual(unverified.verify_mode, ssl.CERT_NONE)

    def test_match_hostname_stays_removed_like_cpython(self):
        self.assertFalse(hasattr(ssl, "match_hostname"))
        self.assertNotIn("match_hostname", ssl.__all__)

    def test_client_auth_context_trusts_only_what_the_caller_loads(self):
        with patch.dict(os.environ, {}, clear=False):
            for name in ("SSL_CERT_FILE", "SSL_CERT_DIR", "PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE"):
                os.environ.pop(name, None)
            os.environ["SSL_CERT_FILE"] = str(CERTDATA / "pycacert.pem")
            server = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            client = ssl.create_default_context()
        required = ssl.VERIFY_X509_PARTIAL_CHAIN | ssl.VERIFY_X509_STRICT
        self.assertEqual(server.verify_mode, ssl.CERT_NONE)
        self.assertEqual(server.cert_store_stats()["x509_ca"], 0)
        self.assertEqual(server.verify_flags & required, required)
        self.assertEqual(client.verify_flags & required, required)
        self.assertGreater(client.cert_store_stats()["x509_ca"], 0)
        server.verify_mode = ssl.CERT_REQUIRED
        server.load_verify_locations(cafile=str(CERTDATA / "pycacert.pem"))
        self.assertGreater(server.cert_store_stats()["x509_ca"], 0)


if __name__ == "__main__":
    unittest.main()
