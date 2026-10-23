from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch


CERTDATA = Path(sys.argv.pop(1))
PINNED_BUNDLE = Path(sys.argv.pop(1))
REFERENCE_PYTHON = Path(sys.argv.pop(1))
SCRATCH = Path(os.environ["TMPDIR"])
ROOT_CERT = CERTDATA / "capath" / "b1930218.0"


class TrustPolicyContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import ssl

        cls.ssl = ssl
        cls.bundle = Path(ssl.__file__).with_name("python-build-cacert.pem")
        if not ROOT_CERT.is_file():
            raise FileNotFoundError(ROOT_CERT)
        if not PINNED_BUNDLE.is_file():
            raise FileNotFoundError(PINNED_BUNDLE)
        if not REFERENCE_PYTHON.is_file():
            raise FileNotFoundError(REFERENCE_PYTHON)

    def new_context(self):
        return self.ssl.SSLContext(self.ssl.PROTOCOL_TLS_CLIENT)

    def isolated_context_stats(self, flags: tuple[str, ...], env: dict[str, str]) -> dict:
        code = (
            "import json, ssl; "
            "ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT); "
            "ctx.load_default_certs(); "
            "print(json.dumps(ctx.cert_store_stats()))"
        )
        environment = os.environ.copy()
        for name in (
            "SSL_CERT_FILE",
            "SSL_CERT_DIR",
            "PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE",
        ):
            environment.pop(name, None)
        environment.update(env)
        result = subprocess.run(
            [sys.executable, *flags, "-c", code],
            check=True,
            capture_output=True,
            env=environment,
            text=True,
        )
        import json

        return json.loads(result.stdout)

    def test_real_locked_bundle_is_installed_and_used(self) -> None:
        self.assertEqual(self.bundle.read_bytes(), PINNED_BUNDLE.read_bytes())
        missing_paths = self.ssl.DefaultVerifyPaths(
            None, None, "SSL_CERT_FILE", "", "SSL_CERT_DIR", ""
        )
        with (
            patch.dict(os.environ, {}, clear=False),
            patch.object(
                self.ssl.SSLContext, "set_default_verify_paths", lambda context: None
            ),
            patch.object(
                self.ssl, "get_default_verify_paths", return_value=missing_paths
            ),
        ):
            for name in (
                "SSL_CERT_FILE",
                "SSL_CERT_DIR",
                "PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE",
            ):
                os.environ.pop(name, None)
            context = self.new_context()
            context.load_default_certs()
        self.assertEqual(
            context.get_ca_certs(binary_form=True),
            self.new_context_with_bundle().get_ca_certs(binary_form=True),
        )

    def new_context_with_bundle(self):
        context = self.new_context()
        context.load_verify_locations(cafile=str(self.bundle))
        return context

    def test_configured_system_paths_precede_bundle(self) -> None:
        paths = self.ssl.get_default_verify_paths()
        if paths.cafile is None and paths.capath is None:
            self.skipTest("configured system CA paths are unavailable")
        loaded_paths = []
        load_verify_locations = self.ssl.SSLContext.load_verify_locations

        def track_load(context, cafile=None, capath=None, cadata=None):
            loaded_paths.append((cafile, capath))
            return load_verify_locations(context, cafile, capath, cadata)

        with (
            patch.dict(os.environ, {}, clear=False),
            patch.object(self.ssl.SSLContext, "load_verify_locations", track_load),
        ):
            for name in (
                "SSL_CERT_FILE",
                "SSL_CERT_DIR",
                "PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE",
            ):
                os.environ.pop(name, None)
            context = self.new_context()
            context.load_default_certs()
        self.assertGreater(context.cert_store_stats()["x509_ca"], 0)
        self.assertNotIn((str(self.bundle), None), loaded_paths)
        self.assertTrue(any(cafile or capath for cafile, capath in loaded_paths))

    def test_default_path_tuple_matches_pinned_reference_environment(self) -> None:
        environment = {
            "SSL_CERT_FILE": os.fspath(ROOT_CERT),
            "SSL_CERT_DIR": os.fspath(SCRATCH / "missing-capath"),
        }
        result = subprocess.run(
            [
                os.fspath(REFERENCE_PYTHON),
                "-I",
                "-B",
                "-c",
                "import json, ssl; p=ssl.get_default_verify_paths(); "
                "print(json.dumps(list(p)))",
            ],
            check=True,
            capture_output=True,
            env=environment,
            text=True,
        )
        import json

        reference = json.loads(result.stdout)
        with patch.dict(os.environ, environment, clear=True):
            candidate = list(self.ssl.get_default_verify_paths())
        self.assertEqual(
            candidate,
            [
                reference[0],
                reference[1],
                reference[2],
                "/etc/ssl/cert.pem",
                reference[4],
                "/etc/ssl/certs",
            ],
        )

    def test_empty_invalid_and_opted_out_sources_suppress_fallback(self) -> None:
        cases = (
            {"SSL_CERT_FILE": ""},
            {"SSL_CERT_FILE": str(SCRATCH / "missing-cafile.pem")},
            {"SSL_CERT_DIR": ""},
            {"SSL_CERT_DIR": str(SCRATCH / "missing-capath")},
            {"PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE": "1"},
        )
        missing_paths = self.ssl.DefaultVerifyPaths(
            None, None, "SSL_CERT_FILE", "", "SSL_CERT_DIR", ""
        )
        for environment in cases:
            with self.subTest(environment=environment):
                with (
                    patch.dict(os.environ, environment, clear=False),
                    patch.object(
                        self.ssl.SSLContext,
                        "set_default_verify_paths",
                        lambda context: None,
                    ),
                    patch.object(
                        self.ssl,
                        "get_default_verify_paths",
                        return_value=missing_paths,
                    ),
                ):
                    for name in (
                        "SSL_CERT_FILE",
                        "SSL_CERT_DIR",
                        "PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE",
                    ):
                        if name not in environment:
                            os.environ.pop(name, None)
                    context = self.new_context()
                    context.load_default_certs()
                self.assertEqual(context.cert_store_stats()["x509"], 0)

    def test_valid_explicit_file_suppresses_fallback(self) -> None:
        environment = os.environ.copy()
        for name in (
            "SSL_CERT_FILE",
            "SSL_CERT_DIR",
            "PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE",
        ):
            environment.pop(name, None)
        environment["SSL_CERT_FILE"] = str(ROOT_CERT)
        environment["SSL_CERT_DIR"] = str(SCRATCH / "missing-capath")
        with patch.dict(os.environ, environment, clear=True):
            context = self.new_context()
            context.load_default_certs()
        self.assertEqual(context.cert_store_stats()["x509_ca"], 1)

    def test_explicit_paths_survive_environment_isolation(self) -> None:
        for flags in (("-E",), ("-I",)):
            with self.subTest(flags=flags):
                stats = self.isolated_context_stats(
                    flags,
                    {
                        "SSL_CERT_FILE": "",
                        "SSL_CERT_DIR": str(SCRATCH / "missing-capath"),
                    },
                )
                self.assertEqual(stats["x509"], 0)

    def test_capath_lookup_uses_hashed_paths_and_caches_first_use(self) -> None:
        import socket
        import threading

        def exchange(context, after_connect=None):
            server_context = self.ssl.SSLContext(self.ssl.PROTOCOL_TLS_SERVER)
            server_context.load_cert_chain(str(CERTDATA / "keycert3.pem"))
            listener = socket.socket()
            listener.settimeout(5)
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            server_errors = []

            def serve():
                try:
                    raw, _ = listener.accept()
                    raw.settimeout(5)
                    with server_context.wrap_socket(raw, server_side=True) as peer:
                        message = peer.recv(1)
                        if message:
                            peer.sendall(message)
                except (OSError, self.ssl.SSLError) as error:
                    server_errors.append(error)
                finally:
                    listener.close()

            thread = threading.Thread(target=serve, daemon=True)
            thread.start()
            accepted = False
            try:
                raw = socket.create_connection(listener.getsockname(), timeout=5)
                peer = context.wrap_socket(
                    raw,
                    server_hostname="localhost",
                    do_handshake_on_connect=False,
                )
                if after_connect is not None:
                    after_connect()
                try:
                    peer.do_handshake()
                    peer.sendall(b"x")
                    accepted = peer.recv(1) == b"x"
                except self.ssl.SSLError:
                    accepted = False
                finally:
                    peer.close()
            finally:
                thread.join(6)
            if thread.is_alive():
                raise TimeoutError("TLS server did not finish")
            if accepted and server_errors:
                raise RuntimeError(f"TLS server failed after handshake: {server_errors[0]}")
            return accepted

        def context_for(capath):
            context = self.new_context()
            context.load_verify_locations(capath=capath)
            self.assertEqual(context.cert_store_stats()["x509"], 0)
            return context

        with tempfile.TemporaryDirectory(prefix="rtls-capath-", dir=SCRATCH) as root:
            capath = Path(root)
            correct = capath / "b1930218.0"
            wrong_name = capath / "ffffffff.0"
            shutil.copyfile(ROOT_CERT, wrong_name)
            context = context_for(os.fsencode(capath))
            self.assertFalse(exchange(context))
            self.assertEqual(context.cert_store_stats()["x509"], 0)

            wrong_name.unlink()
            correct.write_bytes(
                ROOT_CERT.read_bytes()
                + b"\n-----BEGIN CERTIFICATE-----\nZm9v"
            )
            context = context_for(str(capath))
            self.assertFalse(exchange(context))
            self.assertEqual(context.cert_store_stats()["x509"], 0)

            correct.unlink()
            shutil.copyfile(ROOT_CERT, correct)
            context = context_for(str(capath))
            self.assertTrue(exchange(context))
            self.assertEqual(context.cert_store_stats()["x509"], 1)

            context = context_for(str(capath))

            def remove_before_lookup():
                correct.unlink()

            self.assertFalse(exchange(context, remove_before_lookup))
            self.assertEqual(context.cert_store_stats()["x509"], 0)

            context = context_for(str(capath))

            def add_before_lookup():
                shutil.copyfile(ROOT_CERT, correct)

            self.assertTrue(exchange(context, add_before_lookup))
            self.assertEqual(context.cert_store_stats()["x509"], 1)
            correct.unlink()
            self.assertTrue(exchange(context))
            self.assertEqual(context.cert_store_stats()["x509"], 1)

            shutil.copyfile(CERTDATA / "capath" / "4e1295a3.0", correct)
            context = context_for(str(capath))
            self.assertFalse(exchange(context))
            self.assertEqual(context.cert_store_stats()["x509"], 1)

            correct.unlink()
            first = capath / "first"
            second = capath / "second"
            first.mkdir()
            second.mkdir()
            context = context_for(os.pathsep.join((str(first), str(second))))
            shutil.copyfile(ROOT_CERT, second / "b1930218.0")
            self.assertTrue(exchange(context))
            self.assertEqual(context.cert_store_stats()["x509"], 1)

            env_valid = capath / "env-valid"
            env_missing = capath / "env-missing"
            env_valid.mkdir()
            shutil.copyfile(ROOT_CERT, env_valid / "b1930218.0")
            default_environment = {
                "SSL_CERT_FILE": "",
                "SSL_CERT_DIR": os.pathsep.join((str(env_missing), str(env_valid))),
            }
            with patch.dict(os.environ, default_environment, clear=True):
                context = self.ssl.create_default_context()
            self.assertEqual(context.cert_store_stats()["x509"], 0)
            self.assertTrue(exchange(context))
            self.assertEqual(context.cert_store_stats()["x509"], 1)

            missing_environment = {
                "SSL_CERT_FILE": "",
                "SSL_CERT_DIR": os.pathsep.join(
                    (str(env_missing), str(capath / "still-missing"))
                ),
            }
            with patch.dict(os.environ, missing_environment, clear=True):
                context = self.ssl.create_default_context()
            self.assertEqual(context.cert_store_stats()["x509"], 0)
            self.assertFalse(exchange(context))
            self.assertEqual(context.cert_store_stats()["x509"], 0)

        with tempfile.TemporaryDirectory(prefix="rtls-missing-capath-", dir=SCRATCH) as root:
            context = context_for(str(Path(root) / "missing"))
            self.assertEqual(context.cert_store_stats()["x509"], 0)

    def test_ca_stats_include_openssl_legacy_v1_roots(self) -> None:
        context = self.new_context()
        for name in ("b1930218.0", "4e1295a3.0"):
            context.load_verify_locations(cadata=(CERTDATA / "capath" / name).read_bytes())
        self.assertEqual(
            context.cert_store_stats(),
            {"x509": 2, "x509_ca": 2, "crl": 0},
        )
        self.assertEqual(len(context.get_ca_certs(binary_form=True)), 2)

    def test_failed_multi_source_load_preserves_existing_roots(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rtls-cadata-", dir=SCRATCH) as root:
            cafile = Path(root) / "root.pem"
            shutil.copyfile(ROOT_CERT, cafile)
            context = self.new_context()
            context.load_verify_locations(cafile=str(cafile))
            before = context.get_ca_certs(binary_form=True)
            with self.assertRaises(self.ssl.SSLError):
                context.load_verify_locations(cafile=str(cafile), cadata=b"invalid DER")
        self.assertEqual(context.get_ca_certs(binary_form=True), before)

    def test_default_client_flags_include_trusted_first(self) -> None:
        context = self.ssl.create_default_context()
        self.assertTrue(
            context.verify_flags & self.ssl.VERIFY_X509_TRUSTED_FIRST
        )

    def test_purpose_validation_matches_cpython(self) -> None:
        for method in (
            self.ssl.create_default_context,
            self.ssl._create_unverified_context,
        ):
            for value in (None, "SERVER_AUTH"):
                with self.subTest(method=method.__name__, value=value):
                    with self.assertRaises(TypeError):
                        method(purpose=value)
            unknown = self.ssl._ASN1Object._make((1, "UNKNOWN", "unknown", "1.2.3.4"))
            with self.subTest(method=method.__name__, value=unknown):
                with self.assertRaises(ValueError):
                    method(purpose=unknown)

        with self.assertRaises(TypeError):
            self.new_context().load_default_certs(None)

    def test_http_client_skips_unsupported_post_handshake_auth(self) -> None:
        import http.client

        context = http.client._create_https_context(11)
        self.assertIsNone(context.post_handshake_auth)

    def test_concurrent_certificate_loads_do_not_share_mutable_builders(self) -> None:
        context = self.ssl.SSLContext(self.ssl.PROTOCOL_TLS)
        certificate = CERTDATA / "keycert3.pem"
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(
                executor.map(
                    lambda _: context.load_cert_chain(str(certificate)),
                    range(8),
                )
            )
        self.assertEqual(results, [None] * 8)

    def test_hostname_flags_and_post_handshake_auth_policy(self) -> None:
        context = self.new_context()
        with self.assertRaises(ValueError):
            context.verify_mode = self.ssl.CERT_NONE
        self.assertEqual(context.verify_mode, self.ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

        context.check_hostname = False
        context.verify_mode = self.ssl.CERT_NONE
        context.check_hostname = True
        self.assertEqual(context.verify_mode, self.ssl.CERT_REQUIRED)
        context.hostname_checks_common_name = False
        self.assertFalse(context.hostname_checks_common_name)

        with self.assertRaises(NotImplementedError):
            context.post_handshake_auth = True
        self.assertIsNone(context.post_handshake_auth)
        with self.assertRaises(NotImplementedError):
            context.post_handshake_auth = False
        with self.assertRaises(ValueError):
            context.wrap_bio(self.ssl.MemoryBIO(), self.ssl.MemoryBIO())


if __name__ == "__main__":
    unittest.main()
