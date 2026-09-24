"""Structured post-install relocation edits (plan 6): rpaths and sysconfigdata."""
from __future__ import annotations

import shutil
import runpy
import subprocess
import tempfile
import unittest
from pathlib import Path

from buildsys.relocate import (
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
    def test_sysconfig_paths_follow_moved_tree_and_drop_builder_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            libdir = root / "lib" / "python3.14"
            libdir.mkdir(parents=True)
            sysconfigdata = libdir / "_sysconfigdata__linux_x86_64-linux-musl.py"
            sysconfigdata.write_text(
                "build_time_vars = {\n"
                "    'prefix': '/install',\n"
                "    'LIBPL': '/install/lib/python3.14/config-example',\n"
                "    'CC': '/work/llvm/bin/clang',\n"
                "    'LDSHARED': '/work/llvm/bin/clang -bundle -fprofile-instr-use=/work/build/code.profclangd',\n"
                "    'PGO_PROF_GEN_FLAG': '-fprofile-instr-generate',\n"
                "    'PGO_PROF_USE_FLAG': '-fprofile-instr-use=\"$(shell pwd)/code.profclangd\"',\n"
                "    'LLVM_PROF_MERGER': 'llvm-profdata merge -output=code.profclangd',\n"
                "    'LLVM_PROF_FILE': 'LLVM_PROFILE_FILE=code-%p.profclangr',\n"
                "    'PROFILE_TASK': '-m test --pgo -j 9',\n"
                "    'MODULE__SSL_LDFLAGS': '-L/work/build/prefix/lib -lssl -lcrypto',\n"
                "    'CODECS_COMMON_HEADERS': '/work/cpython/Modules/codecs.h',\n"
                "    'UNRELATED': '/installation/data',\n"
                "}\n"
            )
            configdir = libdir / "config-3.14-x86_64-linux-musl"
            configdir.mkdir()
            makefile = configdir / "Makefile"
            makefile.write_text(
                "prefix=/install\n"
                "CONFIG_ARGS= '--prefix=/install'\n"
                "CC= /work/llvm/bin/clang\n"
                "LDFLAGS=\t-L/work/build/prefix/lib -Wl,-z,noexecstack\n"
                "PGO_PROF_GEN_FLAG=-fprofile-instr-generate\n"
                "PGO_PROF_USE_FLAG=-fprofile-instr-use=code.profclangd\n"
                "LLVM_PROF_FILE=LLVM_PROFILE_FILE=code-%p.profclangr\n"
                "LLVM_PROF_MERGER=llvm-profdata merge -output=code.profclangd\n"
                "PROFILE_TASK=-m test --pgo -j 9\n"
                "srcdir= /work/cpython\n"
            )
            binary_dir = root / "bin"
            binary_dir.mkdir()
            config_script = binary_dir / "python3.14-config"
            config_source = (
                "import getopt\nimport sys\nflags = []\n"
                "libs = []\nprint(' '.join(flags))\nprint(' '.join(libs))\n"
            )
            config_script.write_text(config_source)
            library_config_script = configdir / "python-config.py"
            library_config_script.write_text(config_source)

            changed = clean_sysconfig(
                root,
                Path("/work/build/prefix"),
                builder_paths=(Path("/work/build"), Path("/work/cpython"), Path("/work/llvm")),
                command_paths=(Path("/work/llvm/bin/clang"),),
            )

            self.assertIn(sysconfigdata, changed)
            self.assertIn(makefile, changed)
            self.assertIn(config_script, changed)
            self.assertIn(library_config_script, changed)
            rewritten = sysconfigdata.read_text()
            self.assertNotIn("/work/", rewritten)
            self.assertIn("# python-build relocatable sysconfig values", rewritten)
            values = runpy.run_path(str(sysconfigdata))["build_time_vars"]
            resolved_root = root.resolve()
            self.assertEqual(values["prefix"], str(resolved_root))
            self.assertEqual(values["LIBPL"], str(resolved_root / "lib/python3.14/config-example"))
            self.assertEqual(values["CC"], "clang")
            self.assertEqual(values["LDSHARED"], "clang -bundle")
            for key in (
                "PGO_PROF_GEN_FLAG", "PGO_PROF_USE_FLAG", "LLVM_PROF_MERGER",
                "LLVM_PROF_FILE", "PROFILE_TASK",
            ):
                self.assertEqual(values[key], "")
            self.assertEqual(values["MODULE__SSL_LDFLAGS"], "-lssl -lcrypto")
            self.assertEqual(values["CODECS_COMMON_HEADERS"], "")
            self.assertEqual(values["UNRELATED"], "/installation/data")
            rewritten_makefile = makefile.read_text()
            self.assertNotIn("/work/", rewritten_makefile)
            self.assertNotIn("/install", rewritten_makefile)
            self.assertIn(
                "_PYTHON_BUILD_PREFIX := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../../..)",
                rewritten_makefile,
            )
            self.assertIn("prefix=$(_PYTHON_BUILD_PREFIX)", rewritten_makefile)
            for key in (
                "PGO_PROF_GEN_FLAG", "PGO_PROF_USE_FLAG", "LLVM_PROF_MERGER",
                "LLVM_PROF_FILE", "PROFILE_TASK",
            ):
                self.assertRegex(rewritten_makefile, rf"(?m)^{key}=$")
            for script in (config_script, library_config_script):
                self.assertIn("import shlex", script.read_text())
                self.assertIn("print(shlex.join(flags))", script.read_text())
                self.assertIn("print(shlex.join(libs))", script.read_text())


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
