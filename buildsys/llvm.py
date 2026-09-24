"""Verified, selective extraction of the official macOS LLVM archive.

The upstream Apple Silicon release archive contains the full LLVM developer
distribution. Builds need only clang, llvm-profdata, LLVM's archive utilities,
the matching Darwin libLTO, and clang's compiler resources. Keep extraction
streaming and allowlisted so the 7.6 GiB expanded release does not become a
build-time disk requirement.
"""

from __future__ import annotations

import hashlib
import base64
import json
import os
from pathlib import Path, PurePosixPath
import tarfile
import tempfile

from .inputs import InputError

_TOOLS = {
    "bin/clang-23",
    "bin/llvm-profdata",
    "bin/llvm-ar",
    "bin/llvm-nm",
    "bin/llvm-objcopy",
}
_LINKS = {
    "bin/clang": "clang-23",
    "bin/clang++": "clang",
    "bin/llvm-ranlib": "llvm-ar",
    "bin/llvm-strip": "llvm-objcopy",
}
_REQUIRED_FILES = _TOOLS | {
    "lib/libLTO.dylib",
    "lib/clang/23/include/stdint.h",
    "lib/clang/23/lib/darwin/libclang_rt.osx.a",
}
_MAX_MEMBER_BYTES = 256 * 1024 * 1024
_MAX_PREFIX_BYTES = 600 * 1024 * 1024
_CHUNK = 1024 * 1024
LLVM_REPOSITORY = "https://github.com/llvm/llvm-project"


def _archive_identity(archive: Path, sha256: str, size: int) -> None:
    digest = hashlib.sha256()
    found_size = 0
    with Path(archive).open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
            found_size += len(chunk)
    found = digest.hexdigest()
    if found_size != size:
        raise InputError(
            f"LLVM archive size mismatch: found {found_size}, expected {size}"
        )
    if found != sha256:
        raise InputError(
            f"LLVM archive SHA-256 mismatch: found {found}, expected {sha256}"
        )


def _selected(relative: str) -> bool:
    return (
        relative in _TOOLS
        or relative in _LINKS
        or relative == "lib/libLTO.dylib"
        or relative == "lib/clang/23"
        or relative.startswith("lib/clang/23/")
    )


def _safe_relative(relative: str) -> PurePosixPath:
    path = PurePosixPath(relative)
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise InputError(f"unsafe LLVM archive member path: {relative!r}")
    return path


def _ensure_directory(root: Path, relative: PurePosixPath) -> Path:
    current = root
    for part in relative.parts:
        current = current / part
        try:
            current.mkdir()
        except FileExistsError:
            if current.is_symlink() or not current.is_dir():
                raise InputError(f"LLVM archive path is not a directory: {current}")
    return current


def extract_llvm_archive(
    archive: Path,
    destination: Path,
    *,
    archive_root: str,
    sha256: str,
    size: int,
    version: str,
) -> Path:
    """Verify and selectively extract the locked LLVM `.tar.xz` archive.

    Only a fixed tool/resource closure is written. Members are read once from
    the xz stream, paths are created beneath a fresh staging directory, and
    symlinks are restricted to the aliases LLVM publishes for these tools.
    """
    archive = Path(archive)
    destination = Path(destination)
    root = PurePosixPath(archive_root)
    if root.is_absolute() or len(root.parts) != 1 or root.parts[0] in (".", ".."):
        raise InputError(f"invalid LLVM archive root: {archive_root!r}")
    _archive_identity(archive, sha256, size)

    marker_path = destination / ".verified.json"
    if destination.exists():
        try:
            marker = json.loads(marker_path.read_text())
        except (OSError, json.JSONDecodeError):
            marker = None
        if marker == {"version": version, "sha256": sha256}:
            return destination
        raise InputError(f"refusing to replace unverified LLVM prefix: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".llvm-extract-", dir=destination.parent
    ) as temporary:
        staged = Path(temporary) / "prefix"
        staged.mkdir()
        extracted_files: set[str] = set()
        extracted_links: dict[str, str] = {}
        prefix_bytes = 0

        try:
            with tarfile.open(archive, mode="r|xz") as tar:
                for member in tar:
                    name = PurePosixPath(member.name)
                    if name.is_absolute() or any(
                        part in ("", ".", "..") for part in name.parts
                    ):
                        if name.parts and name.parts[0] == root.parts[0]:
                            raise InputError(
                                f"unsafe LLVM archive member path: {member.name!r}"
                            )
                        continue
                    if not name.parts or name.parts[0] != root.parts[0]:
                        continue
                    if len(name.parts) == 1:
                        continue
                    relative = PurePosixPath(*name.parts[1:])
                    relative_text = relative.as_posix()
                    if not _selected(relative_text):
                        continue
                    relative = _safe_relative(relative_text)
                    if member.isdir():
                        _ensure_directory(staged, relative)
                        continue
                    if relative_text in extracted_files or relative_text in extracted_links:
                        raise InputError(
                            f"duplicate LLVM archive member: {relative_text}"
                        )
                    if member.issym():
                        expected_link = _LINKS.get(relative_text)
                        if expected_link is None or member.linkname != expected_link:
                            raise InputError(
                                f"unexpected LLVM tool symlink: {relative_text} "
                                f"-> {member.linkname!r}"
                            )
                        target = PurePosixPath(member.linkname)
                        if target.is_absolute() or ".." in target.parts or len(target.parts) != 1:
                            raise InputError(
                                f"unsafe LLVM tool symlink: {relative_text} "
                                f"-> {member.linkname!r}"
                            )
                        extracted_links[relative_text] = member.linkname
                        continue
                    if not member.isfile():
                        raise InputError(
                            f"unsupported LLVM archive member: {relative_text}"
                        )
                    if member.size < 0 or member.size > _MAX_MEMBER_BYTES:
                        raise InputError(
                            f"LLVM archive member exceeds extraction limit: "
                            f"{relative_text} ({member.size} bytes)"
                        )
                    prefix_bytes += member.size
                    if prefix_bytes > _MAX_PREFIX_BYTES:
                        raise InputError(
                            "LLVM selected toolchain exceeds extraction limit "
                            f"({_MAX_PREFIX_BYTES} bytes)"
                        )
                    output = staged.joinpath(*relative.parts)
                    _ensure_directory(staged, relative.parent)
                    source = tar.extractfile(member)
                    if source is None:
                        raise InputError(f"cannot read LLVM archive member: {relative_text}")
                    with source, output.open("xb") as destination_file:
                        remaining = member.size
                        while remaining:
                            chunk = source.read(min(_CHUNK, remaining))
                            if not chunk:
                                raise InputError(
                                    f"truncated LLVM archive member: {relative_text}"
                                )
                            destination_file.write(chunk)
                            remaining -= len(chunk)
                    output.chmod(0o755 if member.mode & 0o111 else 0o644)
                    extracted_files.add(relative_text)
        except (tarfile.TarError, OSError, EOFError) as error:
            raise InputError(f"cannot selectively extract LLVM archive: {error}") from error

        missing_files = sorted(_REQUIRED_FILES - extracted_files)
        missing_links = sorted(set(_LINKS) - extracted_links.keys())
        if missing_files or missing_links:
            raise InputError(
                "LLVM archive is missing required members: "
                + ", ".join([*missing_files, *missing_links])
            )
        for relative, target in extracted_links.items():
            link = staged / relative
            _ensure_directory(staged, PurePosixPath(relative).parent)
            link.symlink_to(target)
        (staged / ".verified.json").write_text(
            json.dumps({"version": version, "sha256": sha256}, sort_keys=True) + "\n"
        )
        os.replace(staged, destination)
    return destination


def verify_llvm_attestation_metadata(
    attestation: Path,
    *,
    archive_filename: str,
    archive_sha256: str,
    release_tag: str,
    source_commit: str,
    workflow: str,
) -> None:
    """Check the hash-pinned Sigstore statement's release and subject fields.

    This validates the statement metadata used by the lock; it does not
    replace cryptographic Sigstore bundle verification.
    """
    try:
        bundle = json.loads(Path(attestation).read_text())
        payload = json.loads(
            base64.b64decode(bundle["dsseEnvelope"]["payload"], validate=True)
        )
    except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError) as error:
        raise InputError(f"invalid LLVM Sigstore provenance bundle: {error}") from error

    if bundle.get("mediaType") != "application/vnd.dev.sigstore.bundle.v0.3+json":
        raise InputError("unexpected LLVM Sigstore bundle media type")
    envelope = bundle.get("dsseEnvelope", {})
    if not envelope.get("signatures"):
        raise InputError("LLVM Sigstore bundle has no DSSE signature")
    verification = bundle.get("verificationMaterial", {})
    certificate = verification.get("certificate", {})
    if not certificate.get("rawBytes") or not verification.get("tlogEntries"):
        raise InputError("LLVM Sigstore bundle lacks certificate or transparency entry")

    subjects = payload.get("subject", [])
    if not any(
        item.get("name") == archive_filename
        and item.get("digest", {}).get("sha256") == archive_sha256
        for item in subjects
    ):
        raise InputError("LLVM provenance subject does not match the pinned archive")
    predicate = payload.get("predicate", {})
    build = predicate.get("buildDefinition", {})
    workflow_parameters = build.get("externalParameters", {}).get("workflow", {})
    if workflow_parameters.get("repository") != LLVM_REPOSITORY:
        raise InputError("LLVM provenance names an unexpected source repository")
    if workflow_parameters.get("ref") != f"refs/tags/{release_tag}":
        raise InputError("LLVM provenance names an unexpected release tag")
    resolved = build.get("resolvedDependencies", [])
    if not any(
        item.get("uri") == f"git+{LLVM_REPOSITORY}@refs/tags/{release_tag}"
        and item.get("digest", {}).get("gitCommit") == source_commit
        for item in resolved
    ):
        raise InputError("LLVM provenance source commit does not match the lock")
    if predicate.get("runDetails", {}).get("builder", {}).get("id") != workflow:
        raise InputError("LLVM provenance builder workflow does not match the lock")
