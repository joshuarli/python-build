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
        self.assertIn(
            "-pthread",
            driver["cflags_for"]("zstd", TARGETS["x86_64-unknown-linux-musl"]),
        )

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
