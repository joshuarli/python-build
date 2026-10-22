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
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import stat
import tarfile
import tempfile

from .inputs import InputError

@dataclass(frozen=True)
class ExtractionLayout:
    """The allowlisted tool/resource closure taken from one release archive."""

    tools: frozenset[str]
    links: dict[str, str]
    required: frozenset[str]
    library_files: frozenset[str]
    resource_prefixes: tuple[str, ...]
    max_member_bytes: int
    max_prefix_bytes: int
    resource_files: frozenset[str] = frozenset()

    def selected(self, relative: str) -> bool:
        return (
            relative in self.tools
            or relative in self.links
            or relative in self.library_files
            or relative in self.resource_files
            or relative == "lib/clang/23"
            or any(
                relative == prefix.rstrip("/") or relative.startswith(prefix)
                for prefix in self.resource_prefixes
            )
        )


@dataclass(frozen=True)
class _PrefixManifest:
    directories: dict[str, int]
    files: dict[str, tuple[str, int]]
    links: dict[str, str]
    root_mode: int = 0o755


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

MACOS_AARCH64_LAYOUT = ExtractionLayout(
    tools=frozenset(_TOOLS),
    links=dict(_LINKS),
    required=frozenset(_REQUIRED_FILES),
    library_files=frozenset({"lib/libLTO.dylib"}),
    resource_prefixes=("lib/clang/23/",),
    max_member_bytes=_MAX_MEMBER_BYTES,
    max_prefix_bytes=_MAX_PREFIX_BYTES,
)

# The Linux release links clang and lld statically against LLVM, so no
# libLTO/LLVMgold is needed: lld performs ThinLTO itself. Only the headers
# and the builtins/profile/crt runtimes are taken from the resource tree; the
# sanitizer and Fortran runtimes are left in the archive.
_LINUX_RUNTIME = "lib/clang/23/lib/x86_64-unknown-linux-gnu/"
LINUX_X86_64_LAYOUT = ExtractionLayout(
    tools=frozenset(_TOOLS | {"bin/lld", "bin/llvm-readobj"}),
    links={**_LINKS, "bin/ld.lld": "lld", "bin/llvm-readelf": "llvm-readobj"},
    required=frozenset(_TOOLS | {
        "bin/lld",
        "bin/llvm-readobj",
        "lib/clang/23/include/stdint.h",
        _LINUX_RUNTIME + "libclang_rt.profile.a",
        _LINUX_RUNTIME + "libclang_rt.builtins.a",
    }),
    library_files=frozenset(),
    resource_prefixes=("lib/clang/23/include/",),
    resource_files=frozenset(
        _LINUX_RUNTIME + name for name in (
            "libclang_rt.profile.a",
            "libclang_rt.builtins.a",
            "clang_rt.crtbegin.o",
            "clang_rt.crtend.o",
        )
    ),
    max_member_bytes=320 * 1024 * 1024,
    max_prefix_bytes=900 * 1024 * 1024,
)
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


def _selected_member(layout: ExtractionLayout, relative: str) -> bool:
    return layout.selected(relative)


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
            current.mkdir(mode=0o755)
        except FileExistsError:
            if current.is_symlink() or not current.is_dir():
                raise InputError(f"LLVM archive path is not a directory: {current}")
        current.chmod(0o755)
    return current


def _archive_manifest(
    archive: Path,
    *,
    archive_root: str,
    layout: ExtractionLayout,
    destination: Path | None = None,
) -> _PrefixManifest:
    root = PurePosixPath(archive_root)
    files: dict[str, tuple[str, int]] = {}
    links: dict[str, str] = {}
    directories: set[str] = set()
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
                if not _selected_member(layout, relative_text):
                    continue
                relative = _safe_relative(relative_text)
                if member.isdir():
                    if relative_text in files or relative_text in links:
                        raise InputError(
                            f"conflicting LLVM archive member: {relative_text}"
                        )
                    directories.add(relative_text)
                    continue
                if (
                    relative_text in files
                    or relative_text in links
                    or relative_text in directories
                ):
                    raise InputError(f"duplicate LLVM archive member: {relative_text}")
                if member.issym():
                    expected_link = layout.links.get(relative_text)
                    if expected_link is None or member.linkname != expected_link:
                        raise InputError(
                            f"unexpected LLVM tool symlink: {relative_text} "
                            f"-> {member.linkname!r}"
                        )
                    target = PurePosixPath(member.linkname)
                    if (
                        target.is_absolute()
                        or ".." in target.parts
                        or len(target.parts) != 1
                    ):
                        raise InputError(
                            f"unsafe LLVM tool symlink: {relative_text} "
                            f"-> {member.linkname!r}"
                        )
                    links[relative_text] = member.linkname
                    continue
                if not member.isfile():
                    raise InputError(
                        f"unsupported LLVM archive member: {relative_text}"
                    )
                if member.size < 0 or member.size > layout.max_member_bytes:
                    raise InputError(
                        f"LLVM archive member exceeds extraction limit: "
                        f"{relative_text} ({member.size} bytes)"
                    )
                prefix_bytes += member.size
                if prefix_bytes > layout.max_prefix_bytes:
                    raise InputError(
                        "LLVM selected toolchain exceeds extraction limit "
                        f"({layout.max_prefix_bytes} bytes)"
                    )
                source = tar.extractfile(member)
                if source is None:
                    raise InputError(
                        f"cannot read LLVM archive member: {relative_text}"
                    )
                digest = hashlib.sha256()
                with source:
                    remaining = member.size
                    if destination is None:
                        while remaining:
                            chunk = source.read(min(_CHUNK, remaining))
                            if not chunk:
                                raise InputError(
                                    f"truncated LLVM archive member: {relative_text}"
                                )
                            digest.update(chunk)
                            remaining -= len(chunk)
                    else:
                        _ensure_directory(destination, relative.parent)
                        output = destination.joinpath(*relative.parts)
                        with output.open("xb") as destination_file:
                            while remaining:
                                chunk = source.read(min(_CHUNK, remaining))
                                if not chunk:
                                    raise InputError(
                                        f"truncated LLVM archive member: {relative_text}"
                                    )
                                digest.update(chunk)
                                destination_file.write(chunk)
                                remaining -= len(chunk)
                mode = 0o755 if member.mode & 0o111 else 0o644
                files[relative_text] = (digest.hexdigest(), mode)
                if destination is not None:
                    destination.joinpath(*relative.parts).chmod(mode)
    except (tarfile.TarError, OSError, EOFError) as error:
        raise InputError(f"cannot selectively extract LLVM archive: {error}") from error

    missing_files = sorted(layout.required - files.keys())
    missing_links = sorted(set(layout.links) - links.keys())
    if missing_files or missing_links:
        raise InputError(
            "LLVM archive is missing required members: "
            + ", ".join([*missing_files, *missing_links])
        )
    for member in files.keys() | links.keys():
        parts = PurePosixPath(member).parts
        if any(
            "/".join(parts[:index]) in files or "/".join(parts[:index]) in links
            for index in range(1, len(parts))
        ):
            raise InputError(f"LLVM archive member conflicts with a directory: {member}")
    for directory in directories:
        if directory in files or directory in links:
            raise InputError(f"LLVM archive member conflicts with a directory: {directory}")
    for member in files.keys() | links.keys():
        parts = PurePosixPath(member).parts
        directories.update(
            "/".join(parts[:index]) for index in range(1, len(parts))
        )
    directory_modes = {directory: 0o755 for directory in directories}

    if destination is not None:
        for directory in sorted(
            directories, key=lambda item: len(PurePosixPath(item).parts)
        ):
            _ensure_directory(destination, PurePosixPath(directory))
        for relative, target in links.items():
            link = destination / relative
            _ensure_directory(destination, PurePosixPath(relative).parent)
            link.symlink_to(target)

    return _PrefixManifest(directory_modes, files, links)


def _marker_bytes(version: str, sha256: str) -> bytes:
    marker = json.dumps({"version": version, "sha256": sha256}, sort_keys=True)
    return (marker + "\n").encode()


def _manifest_with_marker(
    manifest: _PrefixManifest, version: str, sha256: str
) -> _PrefixManifest:
    files = dict(manifest.files)
    marker_digest = hashlib.sha256(_marker_bytes(version, sha256)).hexdigest()
    files[".verified.json"] = (marker_digest, 0o644)
    return _PrefixManifest(manifest.directories, files, manifest.links)


def _prefix_manifest(root: Path) -> _PrefixManifest:
    root_metadata = root.lstat()
    if not stat.S_ISDIR(root_metadata.st_mode):
        raise InputError(f"LLVM prefix is not a directory: {root}")
    directories: dict[str, int] = {}
    files: dict[str, tuple[str, int]] = {}
    links: dict[str, str] = {}

    def visit(directory: Path, relative_directory: str) -> None:
        with os.scandir(directory) as entries:
            for entry in entries:
                relative = (
                    f"{relative_directory}/{entry.name}"
                    if relative_directory
                    else entry.name
                )
                metadata = entry.stat(follow_symlinks=False)
                mode = metadata.st_mode & 0o7777
                if stat.S_ISDIR(metadata.st_mode):
                    directories[relative] = mode
                    visit(Path(entry.path), relative)
                elif stat.S_ISLNK(metadata.st_mode):
                    links[relative] = os.readlink(entry.path)
                elif stat.S_ISREG(metadata.st_mode):
                    descriptor = os.open(
                        entry.path,
                        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                    )
                    with os.fdopen(descriptor, "rb") as handle:
                        opened = os.fstat(handle.fileno())
                        if not stat.S_ISREG(opened.st_mode):
                            raise InputError(
                                f"LLVM prefix member is not a file: {relative}"
                            )
                        digest = hashlib.sha256()
                        while chunk := handle.read(_CHUNK):
                            digest.update(chunk)
                    files[relative] = (digest.hexdigest(), mode)
                else:
                    raise InputError(f"unsupported LLVM prefix member: {relative}")

    visit(root, "")
    return _PrefixManifest(
        directories,
        files,
        links,
        root_metadata.st_mode & 0o7777,
    )


def _prefix_matches(root: Path, expected: _PrefixManifest) -> bool:
    try:
        return _prefix_manifest(root) == expected
    except (InputError, OSError):
        return False


def extract_llvm_archive(
    archive: Path,
    destination: Path,
    *,
    archive_root: str,
    sha256: str,
    size: int,
    version: str,
    force_recreate: bool = False,
    layout: ExtractionLayout = MACOS_AARCH64_LAYOUT,
) -> Path:
    """Verify, selectively extract, and repair the locked LLVM prefix."""
    archive = Path(archive)
    destination = Path(destination)
    root = PurePosixPath(archive_root)
    if root.is_absolute() or len(root.parts) != 1 or root.parts[0] in (".", ".."):
        raise InputError(f"invalid LLVM archive root: {archive_root!r}")
    if destination.is_symlink():
        raise InputError(f"LLVM prefix destination is a symlink: {destination}")
    _archive_identity(archive, sha256, size)
    archived = _archive_manifest(
        archive, archive_root=archive_root, layout=layout
    )
    expected = _manifest_with_marker(archived, version, sha256)
    if not force_recreate and destination.exists() and _prefix_matches(destination, expected):
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".llvm-extract-", dir=destination.parent
    ) as temporary:
        staged = Path(temporary) / "prefix"
        staged.mkdir(mode=0o755)
        staged.chmod(0o755)
        extracted = _archive_manifest(
            archive,
            archive_root=archive_root,
            layout=layout,
            destination=staged,
        )
        if extracted != archived:
            raise InputError("LLVM archive changed while extracting selected toolchain")
        marker = staged / ".verified.json"
        marker.write_bytes(_marker_bytes(version, sha256))
        marker.chmod(0o644)
        if not _prefix_matches(staged, expected):
            raise InputError("extracted LLVM prefix does not match its archive manifest")

        backup = Path(temporary) / "previous-prefix"
        moved_existing = False
        if destination.exists() or destination.is_symlink():
            os.replace(destination, backup)
            moved_existing = True
        try:
            os.replace(staged, destination)
        except BaseException:
            if moved_existing and not (
                destination.exists() or destination.is_symlink()
            ):
                os.replace(backup, destination)
            raise
    return destination


def verify_llvm_prefix_from_archive(
    archive: Path,
    destination: Path,
    *,
    archive_root: str,
    sha256: str,
    size: int,
    version: str,
    layout: ExtractionLayout = MACOS_AARCH64_LAYOUT,
) -> None:
    """Compare the installed prefix with the selected archive members."""
    archive = Path(archive)
    destination = Path(destination)
    _archive_identity(archive, sha256, size)
    archived = _archive_manifest(
        archive, archive_root=archive_root, layout=layout
    )
    expected = _manifest_with_marker(archived, version, sha256)
    if not _prefix_matches(destination, expected):
        raise InputError(
            f"LLVM prefix does not match the verified archive manifest: {destination}"
        )


def verify_llvm_attestation_metadata(
    attestation: Path,
    *,
    archive_filename: str,
    archive_sha256: str,
    release_tag: str,
    source_commit: str,
    workflow: str,
    workflow_path: str,
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
    if workflow_parameters.get("path") != workflow_path:
        raise InputError("LLVM provenance names an unexpected workflow path")
    resolved = build.get("resolvedDependencies", [])
    if not any(
        item.get("uri") == f"git+{LLVM_REPOSITORY}@refs/tags/{release_tag}"
        and item.get("digest", {}).get("gitCommit") == source_commit
        for item in resolved
    ):
        raise InputError("LLVM provenance source commit does not match the lock")
    if predicate.get("runDetails", {}).get("builder", {}).get("id") != workflow:
        raise InputError("LLVM provenance builder workflow does not match the lock")
