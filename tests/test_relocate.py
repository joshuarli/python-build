"""Structured post-install relocation edits (plan 6): rpaths and sysconfigdata."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from buildsys.relocate import (
    CONSUMER_FLAG_KEYS,
    clean_sysconfig,
    find_elfs,
    is_elf,
    origin_token,
    relocate,
    strip_private_prefix,
)

HAS_PATCHELF = shutil.which("patchelf") is not None


class OriginTokenTests(unittest.TestCase):
    def test_sibling_directory_is_bare_origin(self) -> None:
        self.assertEqual(origin_token(Path("/install/lib/libpython3.14.so.1.0"), Path("/install/lib")), "$ORIGIN")

    def test_bin_to_lib_goes_up_one_level(self) -> None:
        self.assertEqual(origin_token(Path("/install/bin/python3.14"), Path("/install/lib")), "$ORIGIN/../lib")

    def test_nested_extension_module_goes_up_two_levels(self) -> None:
        elf = Path("/install/lib/python3.14/lib-dynload/_ssl.so")
        self.assertEqual(origin_token(elf, Path("/install/lib")), "$ORIGIN/../..")


class StripPrivatePrefixTests(unittest.TestCase):
    def test_removes_include_and_lib_flags(self) -> None:
        text = "-I/work/build/prefix/include -O3 -L/work/build/prefix/lib -lssl"
        cleaned = strip_private_prefix(text, Path("/work/build/prefix"))
        self.assertNotIn("/work/build/prefix", cleaned)
        self.assertIn("-O3", cleaned)
        self.assertIn("-lssl", cleaned)

    def test_removes_bare_archive_path(self) -> None:
        text = "-L/work/build/prefix/lib /work/build/prefix/lib/libffi.a -ldl"
        cleaned = strip_private_prefix(text, Path("/work/build/prefix"))
        self.assertNotIn("/work/build/prefix", cleaned)
        self.assertIn("-ldl", cleaned)

    def test_leaves_unrelated_paths_alone(self) -> None:
        text = "-I/usr/include -L/work/build/prefix/lib"
        cleaned = strip_private_prefix(text, Path("/work/build/prefix"))
        self.assertIn("-I/usr/include", cleaned)


class CleanSysconfigTests(unittest.TestCase):
    def test_strips_consumer_keys_but_preserves_module_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            libdir = root / "lib" / "python3.14"
            libdir.mkdir(parents=True)
            sysconfigdata = libdir / "_sysconfigdata__linux_x86_64-linux-musl.py"
            sysconfigdata.write_text(
                "build_time_vars = {\n"
                "    'LDFLAGS': '-L/work/build/prefix/lib -Wl,-z,noexecstack',\n"
                "    'CFLAGS': '-I/work/build/prefix/include -O3',\n"
                "    'MODULE__SSL_LDFLAGS': '-L/work/build/prefix/lib -lssl -lcrypto',\n"
                "}\n"
            )
            configdir = libdir / "config-3.14-x86_64-linux-musl"
            configdir.mkdir()
            makefile = configdir / "Makefile"
            makefile.write_text("LDFLAGS=\t-L/work/build/prefix/lib -Wl,-z,noexecstack\n")

            changed = clean_sysconfig(root, Path("/work/build/prefix"))

            self.assertIn(sysconfigdata, changed)
            self.assertIn(makefile, changed)
            rewritten = sysconfigdata.read_text()
            self.assertNotIn("/work/build/prefix", rewritten.split("MODULE__SSL_LDFLAGS")[0])
            # Provenance for CPython's own stdlib modules is left alone: it
            # is not part of the pip/distutils extension-build contract.
            self.assertIn("/work/build/prefix/lib -lssl", rewritten)
            self.assertNotIn("/work/build/prefix", makefile.read_text())

    def test_consumer_flag_keys_cover_the_pip_build_surface(self) -> None:
        for key in ("CFLAGS", "LDFLAGS", "LDSHARED", "CPPFLAGS"):
            self.assertIn(key, CONSUMER_FLAG_KEYS)


class ElfDiscoveryTests(unittest.TestCase):
    def test_finds_real_elf_and_skips_symlinks_and_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            elf = root / "bin" / "prog"
            elf.parent.mkdir()
            elf.write_bytes(b"\x7fELF" + b"\x00" * 12)
            text = root / "bin" / "script.sh"
            text.write_text("#!/bin/sh\necho hi\n")
            link = root / "bin" / "alias"
            link.symlink_to(elf)

            found = find_elfs(root)

            self.assertEqual(found, [elf])
            self.assertTrue(is_elf(elf))
            self.assertFalse(is_elf(text))


@unittest.skipUnless(HAS_PATCHELF, "patchelf not installed on this host")
class RelocateIntegrationTests(unittest.TestCase):
    def test_relocate_sets_relative_rpath_on_a_real_elf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bin").mkdir()
            (root / "lib").mkdir()
            elf = root / "bin" / "prog"
            subprocess.run(
                ["cc", "-x", "c", "-o", str(elf), "-"],
                input=b"int main(void){return 0;}",
                check=True,
            )
            touched = relocate(root, Path("/nonexistent/private/prefix"))
            self.assertIn(elf, touched)
            result = subprocess.run(
                ["patchelf", "--print-rpath", str(elf)],
                capture_output=True, text=True, check=True,
            )
            self.assertEqual(result.stdout.strip(), "$ORIGIN/../lib")


if __name__ == "__main__":
    unittest.main()
