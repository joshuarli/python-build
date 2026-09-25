"""Mach-O inspection for the macOS target.

Everything the macOS build asserts about a shipped binary has to come from
its Mach-O header and load commands, not from a compiler banner or a string
search: the architecture actually encoded (`cputype`), the deployment floor
the loader will enforce (`LC_BUILD_VERSION.minos`), which libraries will be
loaded by name, and where the loader will search for them (`LC_RPATH`).

Load commands are parsed here directly rather than scraped from `otool`
output. The parse is small, exact, and testable against synthetic headers,
which matters because the alternative — regexing a tool's human-readable
output — fails open when the tool's format changes. Validation still
cross-checks against the platform tools (`build/package.py`), but the
primitives below stand on their own.

The fat/universal rejection is deliberate: this project ships one arm64
slice. A fat binary would include an unsupported Intel slice in the product.
"""

from __future__ import annotations

import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Thin Mach-O magics, in both byte orders.
_MAGIC_32 = {b"\xce\xfa\xed\xfe": "<", b"\xfe\xed\xfa\xce": ">"}
_MAGIC_64 = {b"\xcf\xfa\xed\xfe": "<", b"\xfe\xed\xfa\xcf": ">"}
# Fat/universal archives, which this project never ships.
_FAT_MAGIC = frozenset({b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",
                        b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca"})

# cputype values (mach/machine.h), including the 64-bit ABI bit.
CPU_ARCH_ABI64 = 0x01000000
CPU_TYPE_X86_64 = 7 | CPU_ARCH_ABI64
CPU_TYPE_ARM64 = 12 | CPU_ARCH_ABI64
CPU_TYPE_ARM64_32 = 12 | 0x02000000
CPU_NAMES = {
    CPU_TYPE_X86_64: "x86_64",
    CPU_TYPE_ARM64: "arm64",
    CPU_TYPE_ARM64_32: "arm64_32",
}

# filetype values.
MH_OBJECT, MH_EXECUTE, MH_DYLIB, MH_BUNDLE = 1, 2, 6, 8
FILETYPE_NAMES = {
    MH_OBJECT: "object", MH_EXECUTE: "execute", MH_DYLIB: "dylib",
    MH_BUNDLE: "bundle", 0x5: "core", 0xb: "dylib_stub",
}

# Load command values.
LC_ID_DYLIB = 0x0D
LC_LOAD_DYLIB = 0x0C
LC_LOAD_WEAK_DYLIB = 0x80000018
LC_REEXPORT_DYLIB = 0x8000001F
LC_RPATH = 0x8000001C
LC_UUID = 0x1B
LC_CODE_SIGNATURE = 0x1D
LC_VERSION_MIN_MACOSX = 0x24
LC_BUILD_VERSION = 0x32
LC_LOAD_UPWARD_DYLIB = 0x80000023

_DEPENDENCY_COMMANDS = frozenset(
    {LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB, LC_REEXPORT_DYLIB, LC_LOAD_UPWARD_DYLIB}
)

# LC_BUILD_VERSION platforms (mach-o/loader.h).
PLATFORM_MACOS = 1
PLATFORM_NAMES = {
    1: "macos", 2: "ios", 3: "tvos", 4: "watchos", 5: "bridgeos",
    6: "maccatalyst", 7: "ios-simulator", 8: "tvos-simulator",
    9: "watchos-simulator", 10: "driverkit", 11: "visionos",
    12: "visionos-simulator",
}

# magic, cputype, cpusubtype, filetype, ncmds, sizeofcmds, flags[, reserved]
_HEADER_FMT = "IiiIIII"
_HEADER_FMT_64 = _HEADER_FMT + "I"


class MachOError(Exception):
    """A file could not be read as a Mach-O image."""


@dataclass(frozen=True)
class MachOHeader:
    path: Path
    magic: int
    cputype: int
    cpusubtype: int
    filetype: int
    flags: int
    is_64: bool

    @property
    def arch(self) -> str:
        return CPU_NAMES.get(self.cputype, f"cputype-{self.cputype}")

    @property
    def kind(self) -> str:
        return FILETYPE_NAMES.get(self.filetype, f"filetype-{self.filetype}")

    @property
    def pie(self) -> bool:
        return bool(self.flags & 0x200000)  # MH_PIE


@dataclass(frozen=True)
class BuildVersion:
    platform: int
    minos: str
    sdk: str

    @property
    def platform_name(self) -> str:
        return PLATFORM_NAMES.get(self.platform, f"platform-{self.platform}")


def format_version(raw: int) -> str:
    """Decode a packed Mach-O version into `major.minor[.patch]`."""
    major = (raw >> 16) & 0xFFFF
    minor = (raw >> 8) & 0xFF
    patch = raw & 0xFF
    return f"{major}.{minor}.{patch}" if patch else f"{major}.{minor}"


def is_macho(path: Path) -> bool:
    """True for a thin Mach-O of either bitness; False for fat images too."""
    try:
        with Path(path).open("rb") as handle:
            magic = handle.read(4)
    except OSError:
        return False
    return magic in _MAGIC_32 or magic in _MAGIC_64


def _magic_of(path: Path) -> bytes:
    try:
        with Path(path).open("rb") as handle:
            magic = handle.read(4)
    except OSError as error:
        raise MachOError(f"cannot read {path}: {error}") from error
    if magic in _FAT_MAGIC:
        raise MachOError(
            f"{path}: fat/universal Mach-O is out of scope; this project ships "
            f"a single arm64 slice"
        )
    return magic


def _header_fields(path: Path) -> tuple[str, bool, tuple]:
    """Byte order, bitness, and the raw header integers for one image."""
    path = Path(path)
    magic = _magic_of(path)
    endian = _MAGIC_64.get(magic) or _MAGIC_32.get(magic)
    if endian is None:
        raise MachOError(f"{path}: not a Mach-O file (magic {magic.hex()})")
    is_64 = magic in _MAGIC_64
    fmt = _HEADER_FMT_64 if is_64 else _HEADER_FMT
    size = struct.calcsize(fmt)
    with path.open("rb") as handle:
        raw = handle.read(size)
    if len(raw) < size:
        raise MachOError(f"{path}: truncated Mach-O header")
    return endian, is_64, struct.unpack(f"{endian}{fmt}", raw)


def read_header(path: Path) -> MachOHeader:
    """Parse the Mach-O header, rejecting malformed or fat images."""
    path = Path(path)
    _endian, is_64, fields = _header_fields(path)
    return MachOHeader(
        path=path, magic=fields[0], cputype=fields[1], cpusubtype=fields[2],
        filetype=fields[3], flags=fields[6], is_64=is_64,
    )


@dataclass(frozen=True)
class LoadCommand:
    cmd: int
    payload: bytes  # command body, excluding cmd/cmdsize
    offset: int = 0  # absolute file offset of the command, including cmd/cmdsize


def load_commands(path: Path) -> list[LoadCommand]:
    """Return every load command, in file order."""
    path = Path(path)
    endian, is_64, fields = _header_fields(path)
    header_size = struct.calcsize(_HEADER_FMT_64 if is_64 else _HEADER_FMT)
    ncmds, sizeofcmds = fields[4], fields[5]
    with path.open("rb") as handle:
        handle.seek(header_size)
        blob = handle.read(sizeofcmds)
    if len(blob) < sizeofcmds:
        raise MachOError(f"{path}: truncated load commands")
    commands: list[LoadCommand] = []
    offset = 0
    for _ in range(ncmds):
        if offset + 8 > len(blob):
            raise MachOError(f"{path}: load command {len(commands)} runs past the header")
        cmd, cmdsize = struct.unpack_from(f"{endian}II", blob, offset)
        if cmdsize < 8 or offset + cmdsize > len(blob):
            raise MachOError(f"{path}: malformed load command size {cmdsize}")
        commands.append(
            LoadCommand(cmd=cmd, payload=blob[offset + 8:offset + cmdsize],
                        offset=header_size + offset)
        )
        offset += cmdsize
    return commands


_LC_HEADER_SIZE = 8  # cmd + cmdsize, which `LoadCommand.payload` excludes


def _string_at(payload: bytes, offset: int) -> str:
    """Resolve a string whose offset is measured from the load command start.

    Mach-O's `lc_str` offsets are relative to the beginning of the command
    (including its 8-byte cmd/cmdsize header), while `LoadCommand.payload`
    begins after that header — so the offset has to be rebased, not used
    directly. Reading it unrebased silently returns a truncated path, which
    would make a wrong dependency name look like a valid one.
    """
    rebased = offset - _LC_HEADER_SIZE
    if rebased < 0 or rebased >= len(payload):
        raise MachOError(f"load command string offset {offset} is outside the command")
    end = payload.find(b"\x00", rebased)
    raw = payload[rebased:] if end == -1 else payload[rebased:end]
    return raw.decode("utf-8", "replace")


def build_version(path: Path) -> BuildVersion | None:
    """The `LC_BUILD_VERSION` (or legacy `LC_VERSION_MIN_MACOSX`) floor, if present."""
    for command in load_commands(path):
        if command.cmd == LC_BUILD_VERSION:
            platform, minos, sdk = struct.unpack_from("<III", command.payload, 0)
            return BuildVersion(platform, format_version(minos), format_version(sdk))
        if command.cmd == LC_VERSION_MIN_MACOSX:
            version, sdk = struct.unpack_from("<II", command.payload, 0)
            return BuildVersion(PLATFORM_MACOS, format_version(version), format_version(sdk))
    return None


def dependencies(path: Path) -> list[str]:
    """Every library this image loads by name (LC_LOAD_DYLIB and friends)."""
    names = []
    for command in load_commands(path):
        if command.cmd in _DEPENDENCY_COMMANDS:
            offset = struct.unpack_from("<I", command.payload, 0)[0]
            names.append(_string_at(command.payload, offset))
    return names


def dylib_id(path: Path) -> str | None:
    """This image's own install name, for a dylib (LC_ID_DYLIB)."""
    for command in load_commands(path):
        if command.cmd == LC_ID_DYLIB:
            offset = struct.unpack_from("<I", command.payload, 0)[0]
            return _string_at(command.payload, offset)
    return None


def rpaths(path: Path) -> list[str]:
    """Every LC_RPATH search path, in file order."""
    found = []
    for command in load_commands(path):
        if command.cmd == LC_RPATH:
            offset = struct.unpack_from("<I", command.payload, 0)[0]
            found.append(_string_at(command.payload, offset))
    return found


def inspect(path: Path) -> dict:
    """A report-ready summary of one Mach-O image."""
    header = read_header(path)
    version = build_version(path)
    return {
        "arch": header.arch,
        "kind": header.kind,
        "is_64": header.is_64,
        "pie": header.pie,
        "platform": version.platform_name if version else None,
        "minos": version.minos if version else None,
        "sdk": version.sdk if version else None,
        "install_name": dylib_id(path),
        "dependencies": dependencies(path),
        "rpaths": rpaths(path),
    }


# --------------------------------------------------------------------------
# Load-command edits.
#
# Every edit here invalidates the binary's code signature. On Apple Silicon a
# Mach-O without a valid signature does not launch at all, so `sign_adhoc`
# is not optional cleanup — an edited-but-unsigned binary is a hard failure,
# not a warning. Callers must edit and re-sign as one operation, which is why
# `resign` defaults to on rather than being something to remember.
# --------------------------------------------------------------------------


def _tool(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise MachOError(
            f"{command[0]} failed on {command[-1]}: {result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout


def set_install_name(path: Path, name: str, *, resign: bool = True) -> None:
    """Set a dylib's own LC_ID_DYLIB (`install_name_tool -id`)."""
    _tool(["install_name_tool", "-id", name, str(path)])
    if resign:
        sign_adhoc(path)


def change_dependency(path: Path, old: str, new: str, *, resign: bool = True) -> None:
    """Rewrite one LC_LOAD_DYLIB entry by name."""
    _tool(["install_name_tool", "-change", old, new, str(path)])
    if resign:
        sign_adhoc(path)


def add_rpath(path: Path, rpath: str, *, resign: bool = True) -> None:
    """Add an LC_RPATH search path; a no-op if already present.

    Requires the image to have been linked with `-headerpad_max_install_names`
    or otherwise have room for the extra load command — `install_name_tool`
    cannot grow the load-command region.
    """
    if rpath in rpaths(path):
        return
    _tool(["install_name_tool", "-add_rpath", rpath, str(path)])
    if resign:
        sign_adhoc(path)


def sign_adhoc(path: Path) -> None:
    """Apply an ad-hoc code signature, replacing any invalidated one."""
    _tool(["codesign", "--force", "--sign", "-", str(path)])


def signature_status(path: Path) -> tuple[bool, str]:
    """(valid, detail) for one image's code signature."""
    result = subprocess.run(
        ["codesign", "--verify", "--strict", str(path)],
        capture_output=True, text=True,
    )
    detail = (result.stderr or result.stdout).strip()
    return result.returncode == 0, detail


def signature_metadata_ranges(path: Path) -> list[tuple[int, int]]:
    """Byte ranges that are signing metadata rather than compiled content.

    An ad-hoc signature covers the whole image and therefore changes whenever
    anything does; the LC_UUID is regenerated per link. Two builds of the same
    source can differ in exactly these bytes and nothing else, which is a very
    different statement from "the builds differ" — this is what lets the
    reproducibility report tell them apart.
    """
    ranges: list[tuple[int, int]] = []
    for command in load_commands(path):
        if command.cmd == LC_UUID:
            ranges.append((command.offset + 8, 16))
        elif command.cmd == LC_CODE_SIGNATURE:
            data_offset, data_size = struct.unpack_from("<II", command.payload, 0)
            if data_size:
                ranges.append((data_offset, data_size))
    return ranges


def normalized_bytes(path: Path) -> bytes:
    """The image with its UUID and signature ranges zeroed."""
    raw = bytearray(Path(path).read_bytes())
    for offset, size in signature_metadata_ranges(path):
        if 0 <= offset < len(raw):
            end = min(offset + size, len(raw))
            raw[offset:end] = b"\x00" * (end - offset)
    return bytes(raw)


def find_machos(root: Path) -> list[Path]:
    """Real (non-symlink) Mach-O images under an installed tree."""
    return sorted(
        path for path in Path(root).rglob("*")
        if path.is_file() and not path.is_symlink() and is_macho(path)
    )
