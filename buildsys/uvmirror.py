"""Release-asset assembly in python-build-standalone layout.

`build/package.py` writes per-target `dist/<triple>/` directories whose archive
names carry this project's local build revision
(`cpython-3.14.6-<triple>-r1.tar.gz`). A public release instead uses Astral's
naming so the assets work as a `uv` python-install mirror:

    cpython-3.14.6+<tag>-<triple>-install_only_stripped.tar.gz

under `releases/download/<tag>/`, plus a `download-metadata.json` subset in
the schema `uv` reads (`crates/uv-python/download-metadata.json`).

Two metadata files are emitted because the smoke test and the release need
different URL bases for the same bytes:

  download-metadata.json  points at this repository's release page, for
                          consumers (`uv python install --python-downloads-json-url ...`).
  smoke-metadata.json     keeps the canonical
                          `github.com/astral-sh/python-build-standalone/releases/download`
                          prefix so `UV_PYTHON_INSTALL_MIRROR=<local dir>`
                          rewrites it to files on disk. `uv` only applies the
                          mirror when the URL carries that exact prefix.

Only the `install_only_stripped` flavor is produced: it is the one `uv`
downloads, and this project's packaged archive is already stripped.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from urllib.parse import quote

VERSION = "3.14.6"


class UvMirrorError(Exception):
    """Release assets could not be assembled from dist/."""


# Every triple this project ships, and the uv metadata key parts for each.
# Keys follow uv's `{impl}-{version}-{os}-{arch}-{libc}` scheme.
TRIPLES: dict[str, dict[str, str]] = {
    "aarch64-apple-darwin": {
        "key_arch": "aarch64",
        "os": "darwin",
        "libc": "none",
    },
    "x86_64-unknown-linux-musl": {
        "key_arch": "x86_64",
        "os": "linux",
        "libc": "musl",
    },
    "aarch64-unknown-linux-musl": {
        "key_arch": "aarch64",
        "os": "linux",
        "libc": "musl",
    },
}

CANONICAL_PREFIX = "https://github.com/astral-sh/python-build-standalone/releases/download"

# Byte sizes of Astral's corresponding CPython 3.14.6 `install_only_stripped`
# archives from the pinned 20260610 release. Keep our release assets within
# 1.2x of these references; this is checked before the files are assembled.
REFERENCE_STRIPPED_ARCHIVE_SIZES_BYTES = {
    "aarch64-apple-darwin": 25_998_180,
    "x86_64-unknown-linux-musl": 28_899_299,
    "aarch64-unknown-linux-musl": 29_147_568,
}


def _require_size_budget(size_bytes: int, triple: str) -> None:
    reference_size = REFERENCE_STRIPPED_ARCHIVE_SIZES_BYTES[triple]
    if size_bytes * 5 > reference_size * 6:
        maximum_size = reference_size * 6 // 5
        raise UvMirrorError(
            f"{triple} archive is {size_bytes} bytes, above the 1.2x limit "
            f"of {maximum_size} bytes for the pinned Astral 20260610 asset"
        )


def asset_name(tag: str, triple: str) -> str:
    """The Astral-format asset name for one triple."""
    return f"cpython-{VERSION}+{tag}-{triple}-install_only_stripped.tar.gz"


def metadata_key(triple: str) -> str:
    """The uv download-metadata.json key for one triple."""
    info = TRIPLES[triple]
    return f"cpython-{VERSION}-{info['os']}-{info['key_arch']}-{info['libc']}"


def metadata_entry(triple: str, tag: str, url_base: str, sha256: str) -> dict:
    """One download-metadata.json entry, matching uv's schema for stable releases."""
    info = TRIPLES[triple]
    name = asset_name(tag, triple)
    return {
        "name": "cpython",
        "arch": {"family": info["key_arch"], "variant": None},
        "os": info["os"],
        "libc": info["libc"],
        "major": 3,
        "minor": 14,
        "patch": 6,
        "prerelease": "",
        "url": f"{url_base.rstrip('/')}/{tag}/{quote(name, safe='')}",
        "sha256": sha256,
        "variant": None,
        "build": tag,
    }


def find_local_archive(dist: Path, triple: str) -> Path:
    """The single packaged archive `build/package.py` produced for a triple."""
    matches = sorted(dist.glob(f"cpython-{VERSION}-{triple}-*.tar.gz"))
    if len(matches) != 1:
        raise UvMirrorError(
            f"expected exactly one packaged archive for {triple} in {dist}, "
            f"found {len(matches)}: run `build/package.py` first"
        )
    return matches[0]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _metadata(tag: str, url_base: str, hashes: dict[str, str]) -> dict:
    return {
        metadata_key(triple): metadata_entry(
            triple, tag, url_base, hashes[asset_name(tag, triple)]
        )
        for triple in TRIPLES
    }


def assemble(tag: str, repo: str, dist: Path, out: Path) -> dict:
    """Copy renamed assets and write checksums plus both metadata files."""
    if not tag or "/" in tag or tag in (".", ".."):
        raise UvMirrorError(f"refusing unsafe release tag {tag!r}")
    out.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    for triple in TRIPLES:
        source = find_local_archive(dist / triple, triple)
        _require_size_budget(source.stat().st_size, triple)
        target = out / asset_name(tag, triple)
        if target.exists():
            raise UvMirrorError(f"refusing to overwrite existing {target}")
        shutil.copyfile(source, target)
        hashes[target.name] = sha256_of(target)
    (out / "SHA256SUMS").write_text(
        "".join(f"{digest}  {name}\n" for name, digest in sorted(hashes.items()))
    )
    release_base = f"https://github.com/{repo}/releases/download"
    (out / "download-metadata.json").write_text(
        json.dumps(_metadata(tag, release_base, hashes), indent=2) + "\n"
    )
    (out / "smoke-metadata.json").write_text(
        json.dumps(_metadata(tag, CANONICAL_PREFIX, hashes), indent=2) + "\n"
    )
    return {
        "tag": tag,
        "assets": sorted(hashes),
        "out": str(out),
    }
