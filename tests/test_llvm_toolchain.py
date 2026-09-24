from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
import base64

from buildsys.inputs import InputError
from buildsys.llvm import extract_llvm_archive, verify_llvm_attestation_metadata


ARCHIVE_ROOT = "LLVM-test-macOS-ARM64"
FILES = {
    "bin/clang-23": b"clang executable",
    "bin/llvm-profdata": b"profdata executable",
    "bin/llvm-ar": b"ar executable",
    "bin/llvm-nm": b"nm executable",
    "bin/llvm-objcopy": b"objcopy executable",
    "lib/libLTO.dylib": b"LTO library",
    "lib/clang/23/include/stdint.h": b"resource header",
    "lib/clang/23/lib/darwin/libclang_rt.osx.a": b"compiler runtime",
    "bin/opt": b"unneeded executable",
    "include/llvm/ADT/StringRef.h": b"unneeded development header",
}
SYMLINKS = {
    "bin/clang": "clang-23",
    "bin/clang++": "clang",
    "bin/llvm-ranlib": "llvm-ar",
    "bin/llvm-strip": "llvm-objcopy",
}


def make_archive(path: Path, files=FILES, symlinks=SYMLINKS, extra_members=()) -> bytes:
    with tarfile.open(path, "w:xz") as archive:
        for relative, payload in files.items():
            member = tarfile.TarInfo(f"{ARCHIVE_ROOT}/{relative}")
            member.size = len(payload)
            member.mode = 0o755 if relative.startswith("bin/") else 0o644
            archive.addfile(member, io.BytesIO(payload))
        for relative, target in symlinks.items():
            member = tarfile.TarInfo(f"{ARCHIVE_ROOT}/{relative}")
            member.type = tarfile.SYMTYPE
            member.linkname = target
            archive.addfile(member)
        for member, payload in extra_members:
            archive.addfile(member, io.BytesIO(payload) if payload is not None else None)
    return path.read_bytes()


class SelectiveExtractionTests(unittest.TestCase):
    def test_extracts_toolchain_closure_and_skips_other_llvm_components(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "llvm.tar.xz"
            raw = make_archive(archive)
            destination = root / "llvm-prefix"

            result = extract_llvm_archive(
                archive,
                destination,
                archive_root=ARCHIVE_ROOT,
                sha256=hashlib.sha256(raw).hexdigest(),
                size=len(raw),
                version="23.1.2",
            )

            self.assertEqual(result, destination)
            for relative, payload in FILES.items():
                path = destination / relative
                if relative.startswith(("bin/opt", "include/")):
                    self.assertFalse(path.exists(), relative)
                else:
                    self.assertEqual(path.read_bytes(), payload, relative)
            self.assertEqual((destination / "bin/clang").readlink(), Path("clang-23"))
            self.assertEqual((destination / "bin/clang++").readlink(), Path("clang"))
            self.assertEqual((destination / "bin/llvm-ranlib").readlink(), Path("llvm-ar"))
            self.assertEqual((destination / "bin/llvm-strip").readlink(), Path("llvm-objcopy"))
            marker = json.loads((destination / ".verified.json").read_text())
            self.assertEqual(marker["version"], "23.1.2")
            self.assertEqual(marker["sha256"], hashlib.sha256(raw).hexdigest())

    def test_digest_mismatch_does_not_publish_prefix(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "llvm.tar.xz"
            raw = make_archive(archive)
            destination = root / "llvm-prefix"

            with self.assertRaises(InputError):
                extract_llvm_archive(
                    archive,
                    destination,
                    archive_root=ARCHIVE_ROOT,
                    sha256="0" * 64,
                    size=len(raw),
                    version="23.1.2",
                )

            self.assertFalse(destination.exists())

    def test_archive_size_mismatch_does_not_publish_prefix(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "llvm.tar.xz"
            raw = make_archive(archive)
            destination = root / "llvm-prefix"

            with self.assertRaises(InputError):
                extract_llvm_archive(
                    archive,
                    destination,
                    archive_root=ARCHIVE_ROOT,
                    sha256=hashlib.sha256(raw).hexdigest(),
                    size=len(raw) + 1,
                    version="23.1.2",
                )

            self.assertFalse(destination.exists())

    def test_unexpected_symlink_is_rejected_without_publishing_prefix(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "llvm.tar.xz"
            symlinks = dict(SYMLINKS)
            symlinks["bin/clang"] = "../../outside"
            raw = make_archive(archive, symlinks=symlinks)
            destination = root / "llvm-prefix"

            with self.assertRaises(InputError):
                extract_llvm_archive(
                    archive,
                    destination,
                    archive_root=ARCHIVE_ROOT,
                    sha256=hashlib.sha256(raw).hexdigest(),
                    size=len(raw),
                    version="23.1.2",
                )

            self.assertFalse(destination.exists())

    def test_traversing_selected_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "llvm.tar.xz"
            malicious_directory = tarfile.TarInfo(
                f"{ARCHIVE_ROOT}/lib/clang/23/../../../../outside"
            )
            malicious_directory.type = tarfile.DIRTYPE
            raw = make_archive(
                archive, extra_members=[(malicious_directory, None)]
            )
            destination = root / "llvm-prefix"

            with self.assertRaises(InputError):
                extract_llvm_archive(
                    archive,
                    destination,
                    archive_root=ARCHIVE_ROOT,
                    sha256=hashlib.sha256(raw).hexdigest(),
                    size=len(raw),
                    version="23.1.2",
                )

            self.assertFalse(destination.exists())
            self.assertFalse((root / "outside").exists())


class AttestationMetadataTests(unittest.TestCase):
    def test_requires_subject_source_commit_and_builder_to_match(self):
        archive_name = "LLVM-23.1.2-macOS-ARM64.tar.xz"
        archive_sha = "a" * 64
        release_tag = "llvmorg-23.1.2"
        source_commit = "b" * 40
        workflow = (
            "https://github.com/llvm/llvm-project/.github/workflows/"
            "release-binaries.yml@refs/tags/llvmorg-23.1.2"
        )
        statement = {
            "subject": [{"name": archive_name, "digest": {"sha256": archive_sha}}],
            "predicate": {
                "buildDefinition": {
                    "externalParameters": {
                        "workflow": {
                            "repository": "https://github.com/llvm/llvm-project",
                            "ref": f"refs/tags/{release_tag}",
                        }
                    },
                    "resolvedDependencies": [{
                        "uri": f"git+https://github.com/llvm/llvm-project@refs/tags/{release_tag}",
                        "digest": {"gitCommit": source_commit},
                    }],
                },
                "runDetails": {"builder": {"id": workflow}},
            },
        }
        bundle = {
            "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
            "dsseEnvelope": {
                "payload": base64.b64encode(json.dumps(statement).encode()).decode(),
                "signatures": [{"sig": "pinned-bundle-signature"}],
            },
            "verificationMaterial": {
                "certificate": {"rawBytes": "pinned-certificate"},
                "tlogEntries": [{}],
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "llvm-provenance.jsonl"
            path.write_text(json.dumps(bundle))
            verify_llvm_attestation_metadata(
                path,
                archive_filename=archive_name,
                archive_sha256=archive_sha,
                release_tag=release_tag,
                source_commit=source_commit,
                workflow=workflow,
            )
            with self.assertRaises(InputError):
                verify_llvm_attestation_metadata(
                    path,
                    archive_filename=archive_name,
                    archive_sha256="c" * 64,
                    release_tag=release_tag,
                    source_commit=source_commit,
                    workflow=workflow,
                )


if __name__ == "__main__":
    unittest.main()
