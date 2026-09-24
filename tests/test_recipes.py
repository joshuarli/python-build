"""Regression tests for native recipe execution boundaries."""
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from buildsys.recipes import Recipe, build_recipe


def _resolved(path: Path) -> Path:
    """Canonicalise a temp path for comparison against recipe output.

    build_recipe resolves the paths it is given, and on macOS `TemporaryDirectory`
    hands back `/var/...` while `resolve()` yields `/private/var/...`, so an
    unresolved expectation compares unequal for reasons that have nothing to do
    with the recipe under test.
    """
    return Path(path).resolve()


class RecipeTests(unittest.TestCase):
    def test_dependency_patch_changes_verified_tree_before_configure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "source.tar"
            with tarfile.open(archive, "w") as output:
                for name, data in (("demo/configure", b"#!/bin/sh\n"),
                                   ("demo/abi.txt", b"ordinary\n")):
                    entry = tarfile.TarInfo(name)
                    entry.size = len(data)
                    entry.mode = 0o755 if name.endswith("configure") else 0o644
                    output.addfile(entry, io.BytesIO(data))
            patch_dir = root / "patches"
            patch_dir.mkdir()
            (patch_dir / "0001-abi.patch").write_text(
                "--- a/abi.txt\n+++ b/abi.txt\n@@ -1 +1 @@\n"
                "-ordinary\n+filc\n"
            )
            recipe = Recipe("demo", "demo", source_subdir="demo",
                            patch_dir=patch_dir, log_path=root / "logs")
            with patch("buildsys.recipes.run") as runner:
                build_recipe(recipe, archive, root / "work", root / "prefix")
            self.assertEqual((root / "work/demo/demo/abi.txt").read_text(), "filc\n")
            self.assertEqual(len(runner.call_args_list), 3)

    def test_sqlite_build_enables_the_standalone_feature_profile(self):
        import runpy

        driver = runpy.run_path(str(Path(__file__).resolve().parents[1] / "build/deps.py"))
        flags = driver["cflags_for"]("sqlite")
        for feature in (
            "SQLITE_ENABLE_FTS3",
            "SQLITE_ENABLE_FTS3_PARENTHESIS",
            "SQLITE_ENABLE_FTS4",
            "SQLITE_ENABLE_FTS5",
            "SQLITE_ENABLE_GEOPOLY",
            "SQLITE_ENABLE_RTREE",
            "SQLITE_ENABLE_DBSTAT_VTAB",
        ):
            with self.subTest(feature=feature):
                self.assertIn(f"-D{feature}", flags)

    def test_zstd_static_library_keeps_multithreading_enabled(self):
        import runpy

        from buildsys.targets import TARGETS

        driver = runpy.run_path(str(Path(__file__).resolve().parents[1] / "build/deps.py"))
        self.assertEqual(driver["make_targets"]("zstd"), ("libzstd.a-mt",))
        self.assertEqual(
            driver["make_variables"]("zstd", TARGETS["x86_64-filc-linux-musl"]),
            ("ZSTD_NO_ASM=1",),
        )
        self.assertEqual(
            driver["make_variables"]("zstd", TARGETS["x86_64-unknown-linux-musl"]),
            (),
        )
        self.assertIn(
            "-pthread",
            driver["cflags_for"]("zstd", TARGETS["x86_64-unknown-linux-musl"]),
        )
        self.assertIn(
            "-DZSTD_DISABLE_ASM=1",
            driver["cflags_for"]("zstd", TARGETS["x86_64-filc-linux-musl"]),
        )
        self.assertNotIn(
            "ZSTD_DISABLE_ASM",
            driver["cflags_for"]("zstd", TARGETS["x86_64-unknown-linux-musl"]),
        )

    def test_filc_openssl_selects_portable_c_implementation(self):
        import runpy
        from buildsys.targets import TARGETS

        driver = runpy.run_path(str(Path(__file__).resolve().parents[1] / "build/deps.py"))
        self.assertEqual(
            driver["configure_args"]("openssl", target=TARGETS["x86_64-filc-linux-musl"]),
            ("no-asm",),
        )
        self.assertEqual(
            driver["configure_args"]("openssl", target=TARGETS["x86_64-unknown-linux-musl"]),
            (),
        )

    def test_filc_xz_disables_both_assembler_paths(self):
        import runpy
        from buildsys.targets import TARGETS

        driver = runpy.run_path(str(Path(__file__).resolve().parents[1] / "build/deps.py"))
        target = TARGETS["x86_64-filc-linux-musl"]
        ordinary = TARGETS["x86_64-unknown-linux-musl"]
        self.assertIn("--disable-assembler", driver["configure_args"]("xz", target=target))
        self.assertEqual(driver["cflags_for"]("xz", target), "-DLZMA_RANGE_DECODER_CONFIG=0")
        self.assertNotIn("--disable-assembler", driver["configure_args"]("xz", target=ordinary))
        self.assertEqual(driver["cflags_for"]("xz", ordinary), "")

    def test_filc_mpdecimal_selects_portable_uint128_machine(self):
        import runpy
        from buildsys.targets import TARGETS

        driver = runpy.run_path(str(Path(__file__).resolve().parents[1] / "build/deps.py"))
        filc = TARGETS["x86_64-filc-linux-musl"]
        ordinary = TARGETS["x86_64-unknown-linux-musl"]
        self.assertIn("MACHINE=uint128", driver["configure_args"]("mpdecimal", target=filc))
        self.assertNotIn("MACHINE=uint128", driver["configure_args"]("mpdecimal", target=ordinary))

    def test_gui_recipes_are_not_selectable(self):
        import runpy
        driver = runpy.run_path(str(Path(__file__).resolve().parents[1] / "build/deps.py"))
        for name in ("tk", "tcl", "libx11", "libxcb", "libxau", "xcb-proto",
                     "xorgproto", "xtrans", "util-macros"):
            self.assertNotIn(name, driver["EXTRACT_DIRS"])
            with self.assertRaises(driver["BuildError"]):
                driver["configure_args"](name, Path("/private"))

    def test_openssl_uses_perl_configure_and_install_sw(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "source.tar"
            with tarfile.open(archive, "w") as output:
                script = tarfile.TarInfo("openssl/Configure")
                script.size = 1
                output.addfile(script, io.BytesIO(b"1"))
            recipe = Recipe("openssl", "openssl", source_subdir="openssl",
                            install="openssl", log_path=root / "logs")
            with patch("buildsys.recipes.run") as runner:
                build_recipe(recipe, archive, root / "work", root / "prefix")
            calls = runner.call_args_list
            self.assertEqual(calls[0].args[0][:2],
                             ["perl", str(_resolved(root / "work/openssl/openssl/Configure"))])
            self.assertIn("no-shared", calls[0].args[0])
            self.assertEqual(calls[-1].args[0], ["make", "install_sw"])

    def test_separate_build_directory_uses_absolute_configure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "source.tar"
            with tarfile.open(archive, "w") as output:
                script = tarfile.TarInfo("db/dist/configure")
                script.size = 10
                script.mode = 0o755
                output.addfile(script, io.BytesIO(b"#!/bin/sh\n"))
            recipe = Recipe("db", "db", source_subdir="db/dist",
                            build_subdir="db/build_unix", log_path=root / "logs")
            with patch("buildsys.recipes.run") as runner:
                build_recipe(recipe, archive, root / "work", root / "prefix")
            self.assertEqual(len(runner.call_args_list), 3)
            expected = _resolved(root / "work/db/db/build_unix")
            for call in runner.call_args_list:
                self.assertEqual(call.kwargs["cwd"], expected)
                self.assertTrue(expected.is_dir())
            configure = Path(runner.call_args_list[0].args[0][0])
            self.assertTrue(configure.is_absolute())
            self.assertEqual(configure.parent.name, "dist")
