from __future__ import annotations

import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from buildsys.patches import apply_patch


REPO = Path(__file__).resolve().parent.parent
PATCH = REPO / "patches" / "package" / "0001-ssl-default-ca-bundle-fallback.patch"
HARNESS = r"""
import json
import sys
sys.path.insert(0, sys.argv[1])
scenario = json.loads(sys.argv[2])
import ssl
events = []
ssl._ssl.get_default_verify_paths = lambda: (
    "SSL_CERT_FILE", scenario["default_cafile"],
    "SSL_CERT_DIR", scenario["default_capath"],
)
ssl.SSLContext.set_default_verify_paths = lambda self: events.append(["defaults"])
ssl.SSLContext.load_verify_locations = lambda self, cafile=None, capath=None, cadata=None: events.append(
    ["bundle", cafile, capath, cadata]
)
ssl.SSLContext.cert_store_stats = lambda self: {
    "x509": 0,
    "x509_ca": 0,
    "x509_crl": 0,
}
context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
context.load_default_certs()
print(json.dumps(events))
"""


@unittest.skipUnless(sys.version_info[:2] == (3, 15), "CPython 3.15 is required")
class SSLFallbackPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source_root = os.environ.get("PYTHON_BUILD_CPYTHON_SOURCE")
        source_ssl = (
            Path(source_root) / "Lib" / "ssl.py"
            if source_root
            else Path(ssl.__file__)
        )
        if not source_ssl.is_file():
            raise unittest.SkipTest(f"CPython source is unavailable: {source_ssl}")
        cls.temporary = tempfile.TemporaryDirectory(
            prefix="ssl-fallback-patch-", dir=os.environ.get("TMPDIR")
        )
        cls.root = Path(cls.temporary.name)
        cls.lib = cls.root / "source" / "Lib"
        cls.lib.mkdir(parents=True)
        shutil.copy2(source_ssl, cls.lib / "ssl.py")
        apply_patch(cls.root / "source", PATCH)
        cls.empty_default_file = cls.root / "empty-default.pem"
        cls.empty_default_file.touch()
        cls.custom_file = cls.root / "custom.pem"
        shutil.copy2(REPO / "tests" / "fixtures" / "localhost.crt", cls.custom_file)
        cls.hashed_directory = cls.root / "hashed-directory"
        cls.hashed_directory.mkdir()
        shutil.copy2(
            REPO / "tests" / "fixtures" / "localhost.crt",
            cls.hashed_directory / "ce275665.0",
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def _load_default_certs(
        self,
        *,
        default_cafile: str | None = None,
        default_capath: str | None = None,
        env: dict[str, str] | None = None,
        flags: tuple[str, ...] = (),
    ) -> list[list[str | None]]:
        process_env = os.environ.copy()
        process_env.pop("SSL_CERT_FILE", None)
        process_env.pop("SSL_CERT_DIR", None)
        process_env.pop("PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE", None)
        process_env.update(env or {})
        result = subprocess.run(
            [
                sys.executable,
                *flags,
                "-S",
                "-c",
                HARNESS,
                str(self.lib),
                json.dumps(
                    {
                        "default_cafile": default_cafile
                        or str(self.root / "missing-default.pem"),
                        "default_capath": default_capath
                        or str(self.root / "missing-default-capath"),
                    }
                ),
            ],
            check=True,
            capture_output=True,
            env=process_env,
            text=True,
        )
        return json.loads(result.stdout)

    def _assert_fallback(self, events: list[list[str | None]]) -> None:
        expected = [
            ["defaults"],
            ["bundle", str(self.lib / "python-build-cacert.pem"), None, None],
        ]
        self.assertEqual(events, expected)

    def _assert_no_fallback(self, events: list[list[str | None]]) -> None:
        self.assertEqual(events, [["defaults"]])

    def test_missing_default_sources_fall_back_after_openssl(self) -> None:
        self._assert_fallback(self._load_default_certs())

    def test_existing_empty_default_file_counts_as_host_configuration(self) -> None:
        self._assert_no_fallback(
            self._load_default_certs(default_cafile=str(self.empty_default_file))
        )

    def test_explicit_custom_file_suppresses_fallback(self) -> None:
        self._assert_no_fallback(
            self._load_default_certs(
                default_cafile=str(self.root / "missing-default.pem"),
                env={"SSL_CERT_FILE": str(self.custom_file)},
            )
        )

    def test_hashed_directory_suppresses_fallback_without_loaded_ca_count(self) -> None:
        self._assert_no_fallback(
            self._load_default_certs(
                default_capath=str(self.hashed_directory),
            )
        )

    def test_empty_and_invalid_explicit_paths_suppress_fallback(self) -> None:
        cases = (
            {"SSL_CERT_FILE": ""},
            {"SSL_CERT_DIR": ""},
            {"SSL_CERT_FILE": str(self.root / "missing-cert.pem")},
            {"SSL_CERT_DIR": str(self.root / "missing-cert-dir")},
        )
        for explicit_paths in cases:
            with self.subTest(explicit_paths=explicit_paths):
                self._assert_no_fallback(self._load_default_certs(env=explicit_paths))

    def test_opt_out_suppresses_fallback(self) -> None:
        self._assert_no_fallback(
            self._load_default_certs(
                env={"PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE": "1"}
            )
        )

    def test_explicit_paths_suppress_fallback_under_environment_isolation(self) -> None:
        for flags in (("-E",), ("-I",)):
            with self.subTest(flags=flags):
                self._assert_no_fallback(
                    self._load_default_certs(
                        env={"SSL_CERT_FILE": "", "SSL_CERT_DIR": "/missing/cert-dir"},
                        flags=flags,
                    )
                )


if __name__ == "__main__":
    unittest.main()
