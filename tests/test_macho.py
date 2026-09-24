"""Mach-O parsing, exercised against synthetic images (plan Section 8.1).

The load commands are built here by hand rather than scraped from a tool so
the assertions pin the *format*, not a tool's current output. The dylib-name
test in particular is a regression test: `lc_str` offsets are relative to the
start of the load command, so reading them against the command body silently
returns a truncated path — which reads like a plausible library name and
would let a wrong dependency through validation.
"""
from __future__ import annotations

import struct
import platform
import subprocess
import sys
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

from buildsys.macho import (
    CPU_TYPE_ARM64, CPU_TYPE_X86_64, LC_BUILD_VERSION, LC_ID_DYLIB,
    LC_LOAD_DYLIB, LC_RPATH, MH_DYLIB, MH_EXECUTE, MachOError, build_version,
    dependencies, dylib_id, find_machos, format_version, inspect, is_macho,
    read_header, rpaths,
)

MH_MAGIC_64 = 0xFEEDFACF


def _pad8(raw: bytes) -> bytes:
    return raw + b"\x00" * (-len(raw) % 8)


def _command(cmd: int, payload: bytes) -> bytes:
    return struct.pack("<II", cmd, 8 + len(payload)) + payload


def dylib_command(cmd: int, name: str) -> bytes:
    raw = _pad8(name.encode() + b"\x00")
    # name offset is measured from the start of the command, which is 8 bytes
    # of cmd/cmdsize followed by four 4-byte dylib fields.
    return _command(cmd, struct.pack("<IIII", 24, 0, 0x10000, 0x10000) + raw)


def rpath_command(path: str) -> bytes:
    raw = _pad8(path.encode() + b"\x00")
    return _command(LC_RPATH, struct.pack("<I", 12) + raw)


def build_version_command(platform: int = 1, minos=(26, 0), sdk=(26, 5)) -> bytes:
    packed = lambda t: (t[0] << 16) | (t[1] << 8) | (t[2] if len(t) > 2 else 0)  # noqa: E731
    return _command(
        LC_BUILD_VERSION,
        struct.pack("<IIII", platform, packed(minos), packed(sdk), 0),
    )


def make_macho(commands, *, cputype: int = CPU_TYPE_ARM64,
               filetype: int = MH_EXECUTE, flags: int = 0x00200000) -> bytes:
    body = b"".join(commands)
    header = struct.pack(
        "<IiiIIIII", MH_MAGIC_64, cputype, 3, filetype, len(commands), len(body), flags, 0
    )
    return header + body


class TempImage:
    """Write image bytes to a temp file for the duration of a test."""

    def __init__(self, data: bytes) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.path = Path(self._directory.name) / "image"
        self.path.write_bytes(data)

    def __enter__(self) -> Path:
        return self.path

    def __exit__(self, *exc) -> None:
        self._directory.cleanup()


class FormatVersionTests(unittest.TestCase):
    def test_packs_major_minor(self) -> None:
        self.assertEqual(format_version((26 << 16) | (0 << 8)), "26.0")

    def test_includes_patch_when_present(self) -> None:
        self.assertEqual(format_version((26 << 16) | (1 << 8) | 3), "26.1.3")


class HeaderTests(unittest.TestCase):
    def test_reads_arch_kind_and_pie(self) -> None:
        with TempImage(make_macho([], cputype=CPU_TYPE_ARM64)) as path:
            header = read_header(path)
        self.assertEqual(header.arch, "arm64")
        self.assertEqual(header.kind, "execute")
        self.assertTrue(header.pie)
        self.assertTrue(header.is_64)

    def test_distinguishes_x86_64(self) -> None:
        with TempImage(make_macho([], cputype=CPU_TYPE_X86_64)) as path:
            self.assertEqual(read_header(path).arch, "x86_64")

    def test_dylib_filetype(self) -> None:
        with TempImage(make_macho([], filetype=MH_DYLIB)) as path:
            self.assertEqual(read_header(path).kind, "dylib")

    def test_non_macho_is_rejected(self) -> None:
        with TempImage(b"\x7fELF" + b"\x00" * 64) as path:
            self.assertFalse(is_macho(path))
            with self.assertRaises(MachOError):
                read_header(path)

    def test_fat_image_is_rejected_not_silently_accepted(self) -> None:
        # A universal binary would mean an Intel slice this project excludes
        # (plan Section 1.4), so it must fail loudly rather than parse as one
        # arbitrary slice.
        fat = b"\xca\xfe\xba\xbe" + b"\x00" * 60
        with TempImage(fat) as path:
            self.assertFalse(is_macho(path))
            with self.assertRaises(MachOError) as caught:
                read_header(path)
            self.assertIn("fat/universal", str(caught.exception))

    def test_truncated_header_is_rejected(self) -> None:
        with TempImage(make_macho([])[:16]) as path:
            with self.assertRaises(MachOError):
                read_header(path)


class LoadCommandTests(unittest.TestCase):
    def test_build_version_reports_floor_and_sdk(self) -> None:
        image = make_macho([build_version_command(1, (26, 0), (26, 5))])
        with TempImage(image) as path:
            version = build_version(path)
        self.assertEqual(version.platform_name, "macos")
        self.assertEqual(version.minos, "26.0")
        self.assertEqual(version.sdk, "26.5")

    def test_dependency_names_are_not_truncated(self) -> None:
        # Regression: an unrebased lc_str offset drops leading path components,
        # turning /usr/lib/libSystem.B.dylib into libSystem.B.dylib.
        image = make_macho([dylib_command(LC_LOAD_DYLIB, "/usr/lib/libSystem.B.dylib")])
        with TempImage(image) as path:
            self.assertEqual(dependencies(path), ["/usr/lib/libSystem.B.dylib"])

    def test_dependency_names_with_rpath_prefix(self) -> None:
        image = make_macho([
            dylib_command(LC_LOAD_DYLIB, "@rpath/libpython3.14.dylib"),
            dylib_command(LC_LOAD_DYLIB, "@loader_path/../lib/libz.1.dylib"),
        ])
        with TempImage(image) as path:
            self.assertEqual(
                dependencies(path),
                ["@rpath/libpython3.14.dylib", "@loader_path/../lib/libz.1.dylib"],
            )

    def test_install_name_is_read(self) -> None:
        image = make_macho([dylib_command(LC_ID_DYLIB, "@rpath/libpython3.14.dylib")],
                           filetype=MH_DYLIB)
        with TempImage(image) as path:
            self.assertEqual(dylib_id(path), "@rpath/libpython3.14.dylib")

    def test_executable_has_no_install_name(self) -> None:
        with TempImage(make_macho([build_version_command()])) as path:
            self.assertIsNone(dylib_id(path))

    def test_rpaths_are_listed(self) -> None:
        image = make_macho([rpath_command("@loader_path/../lib"),
                            rpath_command("/opt/homebrew/lib")])
        with TempImage(image) as path:
            self.assertEqual(rpaths(path), ["@loader_path/../lib", "/opt/homebrew/lib"])

    def test_malformed_command_size_is_rejected(self) -> None:
        body = struct.pack("<II", LC_RPATH, 4)  # cmdsize smaller than the header
        header = struct.pack("<IiiIIIII", MH_MAGIC_64, CPU_TYPE_ARM64, 3, MH_EXECUTE, 1, 8, 0, 0)
        with TempImage(header + body) as path:
            with self.assertRaises(MachOError):
                rpaths(path)

    def test_inspect_summarises_one_image(self) -> None:
        image = make_macho([
            build_version_command(1, (26, 0), (26, 5)),
            dylib_command(LC_ID_DYLIB, "@rpath/libpython3.14.dylib"),
            dylib_command(LC_LOAD_DYLIB, "/usr/lib/libSystem.B.dylib"),
            rpath_command("@loader_path/../lib"),
        ], filetype=MH_DYLIB)
        with TempImage(image) as path:
            summary = inspect(path)
        self.assertEqual(summary["arch"], "arm64")
        self.assertEqual(summary["minos"], "26.0")
        self.assertEqual(summary["install_name"], "@rpath/libpython3.14.dylib")
        self.assertEqual(summary["dependencies"], ["/usr/lib/libSystem.B.dylib"])
        self.assertEqual(summary["rpaths"], ["@loader_path/../lib"])


class FindMachosTests(unittest.TestCase):
    def test_finds_nested_images_and_skips_other_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "bin").mkdir()
            (root / "lib").mkdir()
            (root / "bin" / "python3.14").write_bytes(make_macho([]))
            (root / "lib" / "libpython3.14.dylib").write_bytes(
                make_macho([], filetype=MH_DYLIB)
            )
            (root / "lib" / "python3.14").mkdir()
            (root / "lib" / "python3.14" / "os.py").write_text("pass\n")
            found = {str(p.relative_to(root)) for p in find_machos(root)}
        self.assertEqual(found, {"bin/python3.14", "lib/libpython3.14.dylib"})


class EditCommandTests(unittest.TestCase):
    """The load-command edits must invoke the right tools with the right argv.

    These assert argv construction rather than the effect, because the effect
    needs a real signed binary; a missing import in this path is invisible
    until a full interpreter build reaches relocation, which is far too late
    to discover it.
    """

    def setUp(self) -> None:
        from buildsys import macho
        self.macho = macho
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "image"
        self.path.write_bytes(make_macho([build_version_command()]))
        self.runner = patch("buildsys.macho.subprocess.run")
        self.run = self.runner.start()
        self.run.return_value.returncode = 0
        self.run.return_value.stdout = ""
        self.run.return_value.stderr = ""
        self.addCleanup(self.runner.stop)
        self.addCleanup(self.directory.cleanup)

    def test_set_install_name_edits_then_resigns(self) -> None:
        self.macho.set_install_name(self.path, "@rpath/libpython3.14.dylib")
        commands = [call.args[0] for call in self.run.call_args_list]
        self.assertEqual(commands[0],
                         ["install_name_tool", "-id", "@rpath/libpython3.14.dylib", str(self.path)])
        self.assertEqual(commands[1][:3], ["codesign", "--force", "--sign"])

    def test_change_dependency_rewrites_then_resigns(self) -> None:
        self.macho.change_dependency(self.path, "/install/lib/libpython3.14.dylib",
                                     "@rpath/libpython3.14.dylib")
        commands = [call.args[0] for call in self.run.call_args_list]
        self.assertEqual(commands[0], [
            "install_name_tool", "-change",
            "/install/lib/libpython3.14.dylib", "@rpath/libpython3.14.dylib", str(self.path),
        ])
        self.assertEqual(commands[-1][0], "codesign")

    def test_add_rpath_is_idempotent(self) -> None:
        # The image already carries this rpath, so nothing should be run.
        image = make_macho([rpath_command("@loader_path/../lib")])
        self.path.write_bytes(image)
        self.macho.add_rpath(self.path, "@loader_path/../lib")
        self.run.assert_not_called()

    def test_add_rpath_edits_and_resigns_when_absent(self) -> None:
        self.macho.add_rpath(self.path, "@loader_path/../lib")
        commands = [call.args[0] for call in self.run.call_args_list]
        self.assertEqual(commands[0],
                         ["install_name_tool", "-add_rpath", "@loader_path/../lib", str(self.path)])
        self.assertEqual(commands[-1][0], "codesign")

    def test_a_failing_tool_is_reported_not_ignored(self) -> None:
        self.run.return_value.returncode = 1
        self.run.return_value.stderr = "boom"
        with self.assertRaises(MachOError) as caught:
            self.macho.set_install_name(self.path, "@rpath/x.dylib")
        self.assertIn("boom", str(caught.exception))

    def test_edits_refuse_to_leave_a_stale_signature(self) -> None:
        # On Apple Silicon an edited-but-unsigned Mach-O does not launch, so
        # every edit path must end in a re-sign rather than trusting callers.
        for edit in (
            lambda: self.macho.set_install_name(self.path, "@rpath/x.dylib"),
            lambda: self.macho.change_dependency(self.path, "a", "b"),
            lambda: self.macho.add_rpath(self.path, "@loader_path/lib"),
        ):
            self.run.reset_mock()
            self.run.return_value.returncode = 0
            edit()
            last = self.run.call_args_list[-1].args[0]
            self.assertEqual(last[0], "codesign", f"{last} did not re-sign")


@unittest.skipUnless(sys.platform == "darwin", "host interpreter is not Mach-O")
class HostBinaryTests(unittest.TestCase):
    """The parser must agree with a real binary, not only with synthetic ones."""

    def test_host_interpreter_parses(self) -> None:
        executable = Path(sys.executable)
        if not is_macho(executable):
            # The system Python can be a universal Mach-O. The product parser
            # intentionally rejects fat files, so give it the running host's
            # thin slice rather than weakening that product invariant.
            with tempfile.TemporaryDirectory() as temporary:
                thin = Path(temporary) / "python"
                result = subprocess.run(
                    ["lipo", "-thin", platform.machine(), str(executable), "-output", str(thin)],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                executable = thin
                self._assert_host_interpreter(executable)
            return
        self._assert_host_interpreter(executable)

    def _assert_host_interpreter(self, executable: Path) -> None:
        self.assertTrue(is_macho(executable), f"{executable} is not a thin Mach-O")
        summary = inspect(executable)
        self.assertIn(summary["arch"], {"arm64", "x86_64"})
        self.assertEqual(summary["kind"], "execute")
        self.assertEqual(summary["platform"], "macos")
        self.assertIsNotNone(summary["minos"])


if __name__ == "__main__":
    unittest.main()
