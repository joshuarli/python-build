"""Regression tests for native recipe execution boundaries."""
import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from buildsys.recipes import RECIPE_LAYOUTS, Recipe, Toolchain, build_recipe


def _resolved(path: Path) -> Path:
    """Canonicalise a temp path for comparison against recipe output.

    build_recipe resolves the paths it is given, and on macOS `TemporaryDirectory`
    hands back `/var/...` while `resolve()` yields `/private/var/...`, so an
    unresolved expectation compares unequal for reasons that have nothing to do
    with the recipe under test.
    """
    return Path(path).resolve()


class RecipeTests(unittest.TestCase):
    def test_linux_thinlto_uses_the_pinned_lld_driver(self):
        flags = Toolchain().ldflags(Path('/private'))
        self.assertIn('-fuse-ld=lld', flags)
        self.assertIn('-flto=thin', flags)
        self.assertIn('-Wl,-z,relro', flags)
        self.assertIn('-Wl,-z,now', flags)

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

    def test_mpdecimal_avoids_the_false_x64_probe_on_macos_arm64(self):
        import runpy

        from buildsys.targets import TARGETS

        driver = runpy.run_path(str(Path(__file__).resolve().parents[1] / "build/deps.py"))
        self.assertEqual(
            driver["configure_environment"]("mpdecimal", TARGETS["aarch64-apple-darwin"]),
            (("MACHINE", "uint128"),),
        )
        for triple in ("aarch64-unknown-linux-musl", "x86_64-unknown-linux-musl"):
            with self.subTest(triple=triple):
                self.assertEqual(
                    driver["configure_environment"]("mpdecimal", TARGETS[triple]),
                    (),
                )

    def test_autotools_recipe_passes_configure_environment(self):
        import runpy

        from buildsys.targets import TARGETS

        driver = runpy.run_path(str(Path(__file__).resolve().parents[1] / "build/deps.py"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "source.tar"
            with tarfile.open(archive, "w") as output:
                script = tarfile.TarInfo("mpdecimal-4.0.0/configure")
                script.size = 1
                output.addfile(script, io.BytesIO(b"x"))
            recipe = Recipe(
                "mpdecimal",
                RECIPE_LAYOUTS["mpdecimal"],
                configure_env=driver["configure_environment"](
                    "mpdecimal", TARGETS["aarch64-apple-darwin"]
                ),
                log_path=root / "logs",
            )
            with patch("buildsys.recipes.run") as runner:
                build_recipe(recipe, archive, root / "work", root / "prefix")
            self.assertEqual(
                runner.call_args_list[0].kwargs["env"]["MACHINE"], "uint128"
            )

    def test_gui_recipes_are_not_selectable(self):
        import runpy
        driver = runpy.run_path(str(Path(__file__).resolve().parents[1] / "build/deps.py"))
        for name in ("tk", "tcl", "libx11", "libxcb", "libxau", "xcb-proto",
                     "xorgproto", "xtrans", "util-macros"):
            self.assertNotIn(name, driver["RECIPE_LAYOUTS"])
            with self.assertRaises(driver["BuildError"]):
                driver["configure_args"](name, Path("/private"))

    def test_openssl_uses_perl_configure_and_install_sw(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "source.tar"
            with tarfile.open(archive, "w") as output:
                script = tarfile.TarInfo("openssl-3.5.7/Configure")
                script.size = 1
                output.addfile(script, io.BytesIO(b"1"))
            recipe = Recipe(
                "openssl",
                RECIPE_LAYOUTS["openssl"],
                configure_args=("no-apps", "no-tests"),
                log_path=root / "logs",
            )
            with patch("buildsys.recipes.run") as runner:
                build_recipe(recipe, archive, root / "work", root / "prefix")
            calls = runner.call_args_list
            self.assertEqual(calls[0].args[0][:2],
                             ["perl", str(_resolved(root / "work/openssl/openssl-3.5.7/Configure"))])
            self.assertIn("no-shared", calls[0].args[0])
            self.assertIn("no-apps", calls[0].args[0])
            self.assertIn("no-tests", calls[0].args[0])
            self.assertEqual(calls[1].args[0][-1], "build_sw")
            self.assertEqual(calls[-1].args[0], ["make", "install_sw"])

    def test_openssl_disables_products_that_are_not_shipped(self):
        import runpy

        from buildsys.targets import TARGETS

        driver = runpy.run_path(str(Path(__file__).resolve().parents[1] / "build/deps.py"))
        self.assertEqual(
            driver["configure_args"]("openssl", target=TARGETS["aarch64-unknown-linux-musl"]),
            ("no-apps", "no-tests"),
        )

    def test_separate_build_directory_uses_absolute_configure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "source.tar"
            with tarfile.open(archive, "w") as output:
                script = tarfile.TarInfo("db-6.0.19/dist/configure")
                script.size = 10
                script.mode = 0o755
                output.addfile(script, io.BytesIO(b"#!/bin/sh\n"))
            recipe = Recipe("bdb", RECIPE_LAYOUTS["bdb"], log_path=root / "logs")
            with patch("buildsys.recipes.run") as runner:
                build_recipe(recipe, archive, root / "work", root / "prefix")
            self.assertEqual(len(runner.call_args_list), 3)
            expected = _resolved(root / "work/bdb/db-6.0.19/build_unix")
            for call in runner.call_args_list:
                self.assertEqual(call.kwargs["cwd"], expected)
                self.assertTrue(expected.is_dir())
            configure = Path(runner.call_args_list[0].args[0][0])
            self.assertTrue(configure.is_absolute())
            self.assertEqual(configure.parent.name, "dist")
