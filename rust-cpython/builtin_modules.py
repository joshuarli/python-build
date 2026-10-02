"""Bind declared built-in Rust helpers to Cargo archives and the final core image."""

from __future__ import annotations

import hashlib
import json
import re
import stat
import _struct as struct
import tomllib
from pathlib import Path


class BuiltinArtifactError(ValueError):
    pass


class SourceArtifacts:
    """Check ownership before reading finite source or compiler artifact paths."""

    def __init__(self, object_stores: tuple[Path, ...]):
        self.object_stores = tuple(path.absolute() for path in object_stores)
        self.identities = {(info.st_dev, info.st_ino) for path in object_stores
                           if path.exists() for info in [path.stat()]}

    def owned(self, path: Path, owner: Path, *, missing: bool = False) -> Path:
        path, owner = path.absolute(), owner.absolute()
        if ("objects" in path.parts or ".cache" in path.parts or ".git" in path.parts
                or ".." in path.parts
                or not path.is_relative_to(owner) or not path.resolve().is_relative_to(owner.resolve())):
            raise BuiltinArtifactError(f"unowned artifact path: {path}")
        for part in (path, *path.parents):
            if part.is_symlink():
                raise BuiltinArtifactError(f"symlink in artifact path: {path}")
            if part.exists():
                info = part.stat()
                if (info.st_dev, info.st_ino) in self.identities:
                    raise BuiltinArtifactError(f"object-store alias in artifact path: {path}")
                if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                    raise BuiltinArtifactError(f"hard-linked artifact has ambiguous ownership: {path}")
        if not missing and not path.is_file():
            raise BuiltinArtifactError(f"missing artifact: {path}")
        return path

    def read(self, path: Path, owner: Path) -> bytes:
        return self.owned(path, owner).read_bytes()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def macho_definitions(data: bytes) -> set[str]:
    """Read external section definitions, rejecting undefined and debug symbols."""
    def unpack(format_: str, offset: int):
        width = struct.calcsize(format_)
        if offset < 0 or offset + width > len(data):
            raise BuiltinArtifactError("truncated Mach-O data")
        return struct.unpack_from(format_, data, offset)

    magic, cpu, _, kind, count, length, _, _ = unpack("<8I", 0)
    if magic != 0xfeedfacf or cpu != 0x100000c or kind not in {1, 6}:
        raise BuiltinArtifactError("expected an arm64 Mach-O object or dylib")
    position, end, symbols, sections = 32, 32 + length, None, 0
    if end > len(data):
        raise BuiltinArtifactError("truncated Mach-O load commands")
    for _ in range(count):
        command, size = unpack("<2I", position)
        if size < 8 or position + size > end:
            raise BuiltinArtifactError("invalid Mach-O command bounds")
        if command == 2:
            if size != 24 or symbols is not None:
                raise BuiltinArtifactError("ambiguous Mach-O symbol table")
            symbols = unpack("<4I", position + 8)
        elif command == 0x19:
            if size < 72:
                raise BuiltinArtifactError("truncated Mach-O segment")
            section_count, = unpack("<I", position + 64)
            if 72 + 80 * section_count > size or sections + section_count > 255:
                raise BuiltinArtifactError("invalid Mach-O section table")
            sections += section_count
        position += size
    if position != end or symbols is None:
        raise BuiltinArtifactError("missing Mach-O symbol table")
    offset, count, strings, length = symbols
    if offset + 16 * count > len(data) or strings + length > len(data):
        raise BuiltinArtifactError("invalid Mach-O symbol table bounds")
    result = set()
    for index in range(count):
        name, type_, section, _, _ = unpack("<IBBHQ", offset + 16 * index)
        if type_ & 0xe0 or type_ & 0x10 or not type_ & 1 or type_ & 0x0e != 0x0e:
            continue
        if not 1 <= section <= sections or name >= length:
            raise BuiltinArtifactError("invalid defined Mach-O symbol")
        terminal = data.find(b"\0", strings + name, strings + length)
        if terminal < 0:
            raise BuiltinArtifactError("unterminated Mach-O symbol")
        result.add(data[strings + name:terminal].decode())
    return result


def archive_definitions(data: bytes) -> set[str]:
    """Read object members from a Darwin ar archive, including BSD long names."""
    if not data.startswith(b"!<arch>\n"):
        raise BuiltinArtifactError("expected a Cargo ar archive")
    position, result = 8, set()
    while position < len(data):
        header = data[position:position + 60]
        if len(header) != 60 or header[58:60] != b"`\n":
            raise BuiltinArtifactError("invalid archive member header")
        try:
            size = int(header[48:58].strip())
        except ValueError as error:
            raise BuiltinArtifactError("invalid archive member size") from error
        start, end = position + 60, position + 60 + size
        if size < 0 or end > len(data):
            raise BuiltinArtifactError("truncated archive member")
        member = data[start:end]
        name = header[:16].strip()
        if name.startswith(b"#1/"):
            name_size = int(name[3:])
            if name_size < 0 or name_size > len(member):
                raise BuiltinArtifactError("invalid archive long name")
            member = member[name_size:]
        if member[:4] == b"\xcf\xfa\xed\xfe":
            result.update(macho_definitions(member))
        position = end + (size & 1)
    if position != len(data):
        raise BuiltinArtifactError("invalid archive padding")
    return result


def cargo_library(records: list[dict], manifest: Path, crate: str, kind: str) -> dict:
    candidates = [item for item in records if item.get("reason") == "compiler-artifact"
                  and item.get("manifest_path") == str(manifest)
                  and item.get("target", {}).get("name") == crate
                  and kind in item["target"].get("crate_types", [])]
    if len(candidates) != 1:
        raise BuiltinArtifactError(f"expected one actual Cargo library artifact: {crate}")
    item = candidates[0]
    profile = item["profile"]
    if profile["opt_level"] != "3" or profile["debuginfo"] not in {0, None} or profile["test"]:
        raise BuiltinArtifactError(f"non-release Cargo library: {crate}")
    return item


def selected_builtin_helpers(setup: str, declaration: dict | None) -> list[str]:
    """Every newly eligible static route must have its own artifact proof."""
    placement, placements = None, {}
    for line in setup.splitlines():
        if line.startswith("*"):
            placement = line
        elif line and not line.startswith("#"):
            name = line.split()[0]
            if name in placements:
                raise BuiltinArtifactError("duplicate module registration")
            placements[name] = placement
    expected = {name for name in ("_collections_rs", "_struct_rs")
                if placements.get(name) == "*static*"}
    if declaration is None:
        if expected:
            raise BuiltinArtifactError("built-in helper placement has no explicit declaration")
        return []
    helpers = declaration.get("helpers")
    if (declaration.get("schema") != 1 or not isinstance(helpers, list)
            or not all(isinstance(name, str) for name in helpers)
            or len(helpers) != len(set(helpers)) or set(helpers) != expected):
        raise BuiltinArtifactError("built-in helper declaration does not match static placements")
    return helpers


def verify_builtin_artifacts(source: Path, build: Path, stage: Path, target: str,
                             object_stores: tuple[Path, ...]) -> dict:
    files = SourceArtifacts(object_stores)
    carrier = source / "Modules/cpython-rust-staticlib"
    declaration_path = files.owned(carrier / "builtin-helpers.json", source, missing=True)
    declaration = (json.loads(files.read(declaration_path, source))
                   if declaration_path.exists() else None)
    setup = files.read(source / "Modules/Setup.local", source).decode()
    helpers = selected_builtin_helpers(setup, declaration)
    if not helpers:
        return {}
    if target != "aarch64-apple-darwin":
        raise BuiltinArtifactError("built-in artifact proof target is not implemented")
    manifest = tomllib.loads(files.read(carrier / "Cargo.toml", source).decode())
    config = files.read(build / "Modules/config.c", build).decode()
    workspace = tomllib.loads(files.read(source / "Cargo.toml", source).decode())
    if workspace["profile"]["release"].get("panic") != "abort":
        raise BuiltinArtifactError("built-in carrier requires abort panic")
    receipt_path = build / "rust-staticlib-artifacts.jsonl"
    receipt = files.read(receipt_path, build)
    records = [json.loads(line) for line in receipt.decode().splitlines()]
    if not records or records[-1] != {"reason": "build-finished", "success": True}:
        raise BuiltinArtifactError("Cargo did not finish the static carrier successfully")
    release = build / "target" / target / "release"
    artifact = cargo_library(records, carrier / "Cargo.toml", "cpython_rust_staticlib", "staticlib")
    archives = [Path(name) for name in artifact["filenames"] if name.endswith(".a")]
    if archives != [release / "libcpython_rust_staticlib.a"]:
        raise BuiltinArtifactError("unexpected Cargo carrier archive")
    archive = files.read(archives[0], release)
    archive_symbols = archive_definitions(archive)
    core_path = stage / "lib/libpython3.16.dylib"
    core = files.read(core_path, stage)
    core_symbols = macho_definitions(core)
    result = {"state": "release-carrier-and-core-retained", "cargo_receipt_sha256": digest(receipt),
              "carrier_archive_sha256": digest(archive), "core_image_sha256": digest(core), "helpers": {}}
    for helper in helpers:
        initializer = "_PyInit_" + helper
        dependency = manifest["dependencies"].get(helper)
        if dependency != {"path": "../" + helper}:
            raise BuiltinArtifactError(f"helper is outside the declared static carrier: {helper}")
        registration = r'\{\s*"' + re.escape(helper) + r'"\s*,\s*PyInit_' + re.escape(helper) + r'\s*\}'
        if len(re.findall(registration, config)) != 1:
            raise BuiltinArtifactError(f"missing or duplicate generated built-in registration: {helper}")
        if initializer not in archive_symbols or initializer not in core_symbols:
            raise BuiltinArtifactError(f"initializer not defined in release carrier and final core: {helper}")
        helper_manifest = source / "Modules" / helper / "Cargo.toml"
        item = cargo_library(records, helper_manifest, helper, "rlib")
        rlibs = [Path(name) for name in item["filenames"] if name.endswith(".rlib")]
        if len(rlibs) != 1:
            raise BuiltinArtifactError(f"missing actual helper rlib: {helper}")
        rlib = files.read(rlibs[0], release)
        if initializer not in archive_definitions(rlib):
            raise BuiltinArtifactError(f"helper rlib does not define its initializer: {helper}")
        extension = stage / "lib/python3.16/lib-dynload" / (helper + ".cpython-316-darwin.so")
        files.owned(extension, stage, missing=True)
        if extension.exists():
            raise BuiltinArtifactError(f"built-in helper also has a standalone extension: {helper}")
        result["helpers"][helper] = {"initializer": initializer, "rlib_sha256": digest(rlib),
                                      "cargo_manifest_sha256": digest(files.read(helper_manifest, source)),
                                      "rust_source_sha256": digest(files.read(source / "Modules" / helper / "src/lib.rs", source))}
    return result
