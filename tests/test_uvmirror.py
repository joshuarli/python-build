"""Release-asset assembly in python-build-standalone layout."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from buildsys.uvmirror import (
    REFERENCE_STRIPPED_ARCHIVE_SIZES_BYTES,
    VERSION,
    UvMirrorError,
    assemble,
    asset_name,
    find_local_archive,
    metadata_entry,
    metadata_key,
)


class NamingTests(unittest.TestCase):
    def test_asset_name_matches_astral_install_only_stripped_format(self) -> None:
        self.assertEqual(
            asset_name("20260923", "aarch64-apple-darwin"),
            "cpython-3.14.6+20260923-aarch64-apple-darwin-install_only_stripped.tar.gz",
        )
        self.assertEqual(
            asset_name("20260923", "x86_64-unknown-linux-musl"),
            "cpython-3.14.6+20260923-x86_64-unknown-linux-musl-install_only_stripped.tar.gz",
        )

    def test_metadata_keys_match_uv_scheme(self) -> None:
        self.assertEqual(metadata_key("aarch64-apple-darwin"), "cpython-3.14.6-darwin-aarch64-none")
        self.assertEqual(
            metadata_key("x86_64-unknown-linux-musl"), "cpython-3.14.6-linux-x86_64-musl"
        )
        self.assertEqual(
            metadata_key("aarch64-unknown-linux-musl"), "cpython-3.14.6-linux-aarch64-musl"
        )

    def test_metadata_entry_encodes_plus_like_upstream(self) -> None:
        entry = metadata_entry(
            "aarch64-apple-darwin", "20260923", "https://example.invalid/dl", "0" * 64
        )
        # Upstream percent-encodes the `+` build separator as %2B.
        self.assertEqual(
            entry["url"],
            "https://example.invalid/dl/20260923/"
            "cpython-3.14.6%2B20260923-aarch64-apple-darwin-install_only_stripped.tar.gz",
        )
        self.assertEqual(
            entry,
            {
                "name": "cpython",
                "arch": {"family": "aarch64", "variant": None},
                "os": "darwin",
                "libc": "none",
                "major": 3,
                "minor": 14,
                "patch": 6,
                "prerelease": "",
                "url": entry["url"],
                "sha256": "0" * 64,
                "variant": None,
                "build": "20260923",
            },
        )


class AssembleTests(unittest.TestCase):
    def test_assemble_copies_renamed_assets_and_writes_both_metadata_files(self) -> None:
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            payloads = {
                "aarch64-apple-darwin": b"macos-bytes",
                "x86_64-unknown-linux-musl": b"linux-x64-bytes",
                "aarch64-unknown-linux-musl": b"linux-arm64-bytes",
            }
            for triple, blob in payloads.items():
                triple_dir = root / "dist" / triple
                triple_dir.mkdir(parents=True)
                (triple_dir / f"cpython-{VERSION}-{triple}-r1.tar.gz").write_bytes(blob)
            report = assemble("20260923", "owner/name", root / "dist", root / "release")
            self.assertEqual(report["tag"], "20260923")
            self.assertEqual(len(report["assets"]), 3)

            sums = (root / "release" / "SHA256SUMS").read_text()
            for triple, blob in payloads.items():
                name = asset_name("20260923", triple)
                self.assertIn(f"{hashlib.sha256(blob).hexdigest()}  {name}", sums)
                self.assertEqual((root / "release" / name).read_bytes(), blob)

            release = json.loads((root / "release" / "download-metadata.json").read_text())
            smoke = json.loads((root / "release" / "smoke-metadata.json").read_text())
            self.assertEqual(set(release), set(smoke))
            self.assertIn("cpython-3.14.6-darwin-aarch64-none", release)
            # The release file points at this repo; the smoke file keeps the
            # canonical prefix so UV_PYTHON_INSTALL_MIRROR rewrites it.
            self.assertTrue(
                release["cpython-3.14.6-darwin-aarch64-none"]["url"].startswith(
                    "https://github.com/owner/name/releases/download/20260923/"
                )
            )
            self.assertTrue(
                smoke["cpython-3.14.6-darwin-aarch64-none"]["url"].startswith(
                    "https://github.com/astral-sh/python-build-standalone/releases/download/"
                )
            )
            self.assertEqual(
                release["cpython-3.14.6-linux-x86_64-musl"]["sha256"],
                smoke["cpython-3.14.6-linux-x86_64-musl"]["sha256"],
            )

    def test_assemble_rejects_archives_over_astral_size_budget(self) -> None:
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            for triple in (
                "aarch64-apple-darwin",
                "x86_64-unknown-linux-musl",
                "aarch64-unknown-linux-musl",
            ):
                triple_dir = root / "dist" / triple
                triple_dir.mkdir(parents=True)
                (triple_dir / f"cpython-{VERSION}-{triple}-r1.tar.gz").touch()
            mac_archive = (
                root / "dist" / "aarch64-apple-darwin"
                / f"cpython-{VERSION}-aarch64-apple-darwin-r1.tar.gz"
            )
            maximum_size = (
                REFERENCE_STRIPPED_ARCHIVE_SIZES_BYTES["aarch64-apple-darwin"]
                * 6 // 5
            )
            with mac_archive.open("wb") as handle:
                handle.truncate(maximum_size + 1)

            with self.assertRaisesRegex(UvMirrorError, "1.2x limit"):
                assemble("20260923-budget", "owner/name", root / "dist", root / "release")

    def test_assemble_refuses_missing_or_ambiguous_archives(self) -> None:
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            triple_dir = root / "dist" / "aarch64-apple-darwin"
            triple_dir.mkdir(parents=True)
            with self.assertRaises(UvMirrorError):
                find_local_archive(triple_dir, "aarch64-apple-darwin")
            (triple_dir / f"cpython-{VERSION}-aarch64-apple-darwin-r1.tar.gz").write_bytes(b"a")
            (triple_dir / f"cpython-{VERSION}-aarch64-apple-darwin-r2.tar.gz").write_bytes(b"b")
            with self.assertRaises(UvMirrorError):
                find_local_archive(triple_dir, "aarch64-apple-darwin")

    def test_assemble_refuses_unsafe_tag(self) -> None:
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            with self.assertRaises(UvMirrorError):
                assemble("../evil", "owner/name", root / "dist", root / "release")


if __name__ == "__main__":
    unittest.main()
