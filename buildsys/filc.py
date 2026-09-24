"""Locked Pizfix toolchain for the explicit Fil-C/musl target.

The compiler is a build-host executable. Its sysroot and runtime, including
the loader, are Fil-C/musl; they are the only libc inputs for this target.
"""

from __future__ import annotations

import json
import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .inputs import Cache, Input, InputError, safe_extract
from .recipes import Toolchain


_BUILDER_ASM_HEADERS = Path("/usr/include/x86_64-linux-gnu/asm")
_VERIFIED_MEMBERS = (
    "build/bin/clang",
    "build/bin/clang++",
    "pizfix/lib/libc.so",
    "pizfix/lib/libpizlo.so",
    "pizfix/lib/libyoloc.so",
    "pizfix/lib/ld-fil1-x86_64.so",
    "pizfix/stdfil-include/stdfil.h",
    "pizfix/include/bits/alltypes.h",
)

# The released Pizfix header declares max_align_t with only pointer alignment
# although its x86_64 long double requires 16. This exact header correction
# is applied after verified archive extraction and included in the setup
# marker. Without it, CPython's C ABI alignment check aborts.
_MAX_ALIGN_OLD = b"typedef struct { void *__p; } max_align_t;"
_MAX_ALIGN_NEW = b"typedef union { long double __ld; void *__p; } max_align_t;"


def _correct_max_align_t(prefix: Path) -> None:
    header = prefix / "pizfix/include/bits/alltypes.h"
    before = header.read_bytes()
    if before.count(_MAX_ALIGN_OLD) != 1:
        raise InputError(f"unexpected Pizfix max_align_t declaration: {header}")
    header.write_bytes(before.replace(_MAX_ALIGN_OLD, _MAX_ALIGN_NEW))


def _member_hashes(prefix: Path) -> dict[str, str]:
    hashes = {}
    for name in _VERIFIED_MEMBERS:
        path = prefix / name
        try:
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                while chunk := handle.read(1 << 20):
                    digest.update(chunk)
            hashes[name] = digest.hexdigest()
        except OSError as error:
            raise InputError(f"Fil-C toolchain member unreadable: {path}: {error}") from error
    return hashes


@dataclass(frozen=True)
class FilCToolchain:
    version: str
    release_tag: str
    source_commit: str
    header_correction_commit: str
    archive_root: str
    archive_input: Input
    prefix: Path

    @property
    def pizfix(self) -> Path:
        return self.prefix / "pizfix"

    def require_ready(self) -> None:
        marker = self.prefix / ".python-build-filc.json"
        expected = {"sha256": self.archive_input.sha256, "version": self.version}
        try:
            observed = json.loads(marker.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise InputError(f"Fil-C toolchain is not set up at {self.prefix}; run build.py fetch --target x86_64-filc-linux-musl") from error
        if not isinstance(observed, dict) or any(observed.get(key) != value for key, value in expected.items()):
            raise InputError(f"Fil-C toolchain marker disagrees with lock: {marker}")
        if observed.get("members") != _member_hashes(self.prefix):
            raise InputError(f"Fil-C toolchain member digest mismatch: {self.prefix}")
        if (self.pizfix / "include/bits/alltypes.h").read_bytes().count(_MAX_ALIGN_NEW) != 1:
            raise InputError("Fil-C max_align_t header correction is missing")
        asm = self.pizfix / "os-include/asm"
        if not asm.is_symlink() or asm.readlink() != _BUILDER_ASM_HEADERS:
            raise InputError(f"Fil-C asm UAPI headers need the x86_64 Debian builder: {asm}")
        for path in (
            self.prefix / "build/bin/clang",
            self.prefix / "build/bin/clang++",
            self.pizfix / "lib/libc.so",
            self.pizfix / "lib/libpizlo.so",
            self.pizfix / "lib/libyoloc.so",
            self.pizfix / "lib/ld-fil1-x86_64.so",
        ):
            if not path.exists():
                raise InputError(f"Fil-C toolchain member missing: {path}")

    def toolchain(self, *, jobs: int | None = None) -> Toolchain:
        self.require_ready()
        settings: dict = {
            "cc": str(self.prefix / "build/bin/clang"),
            "cxx": str(self.prefix / "build/bin/clang++"),
            "family": "linux-filc-musl",
            "cpu_baseline": "-march=x86-64",
            "filc_pizfix": self.pizfix,
        }
        # Fil-C itself is a large build and dependency fan-out must stay
        # bounded on shared hosts; callers can explicitly lower this.
        settings["jobs"] = jobs if jobs is not None else 4
        return Toolchain(**settings)


def load_filc_toolchain(path: Path) -> FilCToolchain:
    """Parse the official archive pin and derive its private cache prefix."""
    try:
        document = json.loads(Path(path).read_text())
        section = document["filc_toolchain"]
        archive = section["archive"]
        version = section["version"]
        release_tag = section["release_tag"]
        source_commit = section["source_commit"]
        header_correction_commit = section["header_correction_commit"]
        archive_root = archive["root"]
        if archive_root != f"filc-{version}-linux-x86_64" or section["kind"] != "musl-pizfix":
            raise ValueError("Fil-C archive is not the pinned x86_64 musl/Pizfix layout")
        input_ = Input(
            name="filc-pizfix-x86_64",
            version=version,
            url=archive["url"],
            sha256=archive["sha256"],
            size=archive["size"],
            role="build-source",
            target="x86_64-filc-linux-musl",
            license=archive["license"],
            purpose="Fil-C compiler and musl/Pizfix runtime",
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise InputError(f"invalid Fil-C bootstrap lock {path}: {error}") from error
    if not isinstance(source_commit, str) or len(source_commit) != 40:
        raise InputError(f"invalid Fil-C source commit in {path}")
    if not isinstance(header_correction_commit, str) or len(header_correction_commit) != 40:
        raise InputError(f"invalid Fil-C header correction commit in {path}")
    prefix = Path(path).resolve().parent / ".cache" / "filc" / input_.sha256 / archive_root
    return FilCToolchain(version, release_tag, source_commit,
                         header_correction_commit, archive_root, input_, prefix)


def setup_filc_toolchain(locked: FilCToolchain, cache: Cache) -> Path:
    """Extract verified bytes once, then run upstream's absolute-path setup."""
    archive = cache.require(locked.archive_input)
    if locked.prefix.exists():
        locked.require_ready()
        return locked.prefix
    extracted = safe_extract(archive, locked.prefix.parent)
    prefix = extracted / locked.archive_root
    if prefix != locked.prefix or not (prefix / "setup.sh").is_file():
        raise InputError(f"Fil-C archive has unexpected root: {extracted}")
    result = subprocess.run(
        ["sh", "setup.sh"], cwd=prefix, capture_output=True, text=True
    )
    if result.returncode:
        raise InputError(f"Fil-C setup failed at {prefix}: {result.stderr[-1000:]}")
    # Upstream setup.sh chooses an absolute `asm` UAPI header path from the
    # machine that ran fetch. The Pizfix compiler runs in our x86_64 Debian
    # builder, so make this link describe that build host explicitly.
    asm = locked.pizfix / "os-include/asm"
    asm.unlink()
    asm.symlink_to(_BUILDER_ASM_HEADERS)
    _correct_max_align_t(prefix)
    (prefix / ".python-build-filc.json").write_text(json.dumps({
        "sha256": locked.archive_input.sha256,
        "version": locked.version,
        "members": _member_hashes(prefix),
    }, sort_keys=True) + "\n")
    locked.require_ready()
    return prefix
