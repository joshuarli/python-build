"""Scope exclusions apply to acquisition as well as compilation."""
import tempfile
import unittest
from pathlib import Path

from buildsys.deporder import (
    DEPENDENCY_ORDER, FILC_DEPENDENCY_ORDER, LINUX_DEPENDENCY_ORDER,
    MACOS_DEPENDENCY_ORDER,
)
from buildsys.inputs import load_lock
from buildsys.scope import (
    EXCLUDED_SCRIPT_PREFIXES, EXCLUDED_STDLIB_DIRS, ScopeError,
    enforce_exclusions, probe_in_process, prune_distribution_payload,
    verify_distribution_payload, verify_exclusions,
)

# Tcl/Tk and everything that exists solely to serve its GUI are outside the
# product on every family (plan scope decision).
GUI_CLOSURE = {"tcl", "tk", "libx11", "libxau", "libxcb", "xcb-proto",
               "xorgproto", "xtrans", "util-macros", "libpthread-stubs"}

# Libraries macOS supplies itself; bundling a second copy would shadow the
# platform's and make the artifact less portable, not more (plan Section 5.2).
# Derived from the pinned reference's own Mach-O load commands, which show
# /usr/lib/libz.1.dylib, /usr/lib/libedit.3.dylib, /usr/lib/libncurses.5.4.dylib
# and /usr/lib/libpanel.5.4.dylib and no libexpat — so Expat is bundled from
# source, not taken from the platform.
MACOS_PLATFORM_PROVIDED = {"zlib", "libedit", "ncurses", "libuuid", "bdb"}


class ScopeTests(unittest.TestCase):
    def test_gui_closure_is_not_a_build_or_acquisition_input(self):
        self.assertFalse(GUI_CLOSURE.intersection(LINUX_DEPENDENCY_ORDER))
        self.assertFalse(GUI_CLOSURE.intersection(MACOS_DEPENDENCY_ORDER))
        lock = Path(__file__).resolve().parents[1] / "sources.lock.json"
        self.assertFalse(GUI_CLOSURE.intersection(item.name for item in load_lock(lock)))

    def test_packaging_components_are_not_locked_inputs(self):
        # pip was removed from the lock by the 2026-09-18 decision: an input
        # that is never acquired, built, or shipped does not belong there.
        lock = Path(__file__).resolve().parents[1] / "sources.lock.json"
        names = {item.name for item in load_lock(lock)}
        self.assertNotIn("pip", names)

    def test_macos_does_not_build_libraries_the_platform_provides(self):
        self.assertFalse(MACOS_PLATFORM_PROVIDED.intersection(MACOS_DEPENDENCY_ORDER))

    def test_macos_still_builds_its_private_dependency_set(self):
        # Matches the split measured from the reference's load commands: the
        # libraries it statically links are the ones this project builds.
        for name in ("openssl", "sqlite", "libffi", "bzip2", "xz", "zstd",
                     "mpdecimal", "expat"):
            self.assertIn(name, MACOS_DEPENDENCY_ORDER)

    def test_linux_order_is_unchanged_and_remains_the_default(self):
        # The frozen Linux targets' order is evidence-bearing: it must not
        # drift because a second family was added.
        self.assertIs(DEPENDENCY_ORDER, LINUX_DEPENDENCY_ORDER)
        self.assertIn("bdb", LINUX_DEPENDENCY_ORDER)
        self.assertIn("libuuid", LINUX_DEPENDENCY_ORDER)
        self.assertIn("pkgconf", LINUX_DEPENDENCY_ORDER)
        self.assertIn("ncurses", LINUX_DEPENDENCY_ORDER)

    def test_filc_uses_locked_sqlite_for_dbm(self):
        self.assertNotIn("bdb", FILC_DEPENDENCY_ORDER)
        self.assertIn("sqlite", FILC_DEPENDENCY_ORDER)

    def test_no_order_contains_duplicates(self):
        for order in (LINUX_DEPENDENCY_ORDER, MACOS_DEPENDENCY_ORDER):
            self.assertEqual(len(order), len(set(order)))


class ExclusionEnforcementTests(unittest.TestCase):
    """The pip/ensurepip/venv removal is structural, so it is exercised."""

    def _tree(self, root: Path) -> Path:
        install = root / "install"
        library = install / "lib" / "python3.14"
        library.mkdir(parents=True)
        binary = install / "bin"
        binary.mkdir()
        for name in EXCLUDED_STDLIB_DIRS:
            (library / name).mkdir()
            (library / name / "__init__.py").write_text("")
        (library / "ensurepip" / "_bundled").mkdir()
        (library / "ensurepip" / "_bundled" / "pip-26.1.2-py3-none-any.whl").write_bytes(b"PK")
        (library / "json").mkdir()
        for script in EXCLUDED_SCRIPT_PREFIXES:
            (binary / f"{script}3.14").write_text("#!/install/bin/python3.14\n")
        (binary / "python3.14").write_text("")
        return install

    def test_removes_every_excluded_component(self):
        with tempfile.TemporaryDirectory() as temporary:
            install = self._tree(Path(temporary))
            report = enforce_exclusions(install)
            self.assertTrue(report["removed"])
            self.assertEqual(verify_exclusions(install), [])
            # A bundled wheel is the installer's bytes; removing only the
            # top-level launcher would leave pip in the payload.
            self.assertFalse((install / "lib/python3.14/ensurepip").exists())

    def test_leaves_the_rest_of_the_tree_alone(self):
        with tempfile.TemporaryDirectory() as temporary:
            install = self._tree(Path(temporary))
            enforce_exclusions(install)
            self.assertTrue((install / "bin/python3.14").exists())
            self.assertTrue((install / "lib/python3.14/json").is_dir())

    def test_verification_reports_what_remains(self):
        with tempfile.TemporaryDirectory() as temporary:
            install = self._tree(Path(temporary))
            remaining = verify_exclusions(install)
            self.assertTrue(any("ensurepip" in item for item in remaining))
            self.assertFalse(verify_exclusions.__doc__ is None)

    def test_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            install = self._tree(Path(temporary))
            first = enforce_exclusions(install)
            second = enforce_exclusions(install)
            self.assertTrue(first["removed"])
            self.assertEqual(second["removed"], [])

    def test_a_tree_with_no_stdlib_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            empty = Path(temporary) / "install"
            (empty / "bin").mkdir(parents=True)
            with self.assertRaises(ScopeError):
                enforce_exclusions(empty)

    def test_probe_asks_the_interpreter_not_the_filesystem(self):
        # Filesystem absence is necessary but not sufficient: a stale .pyc or
        # a sys.path entry could still make the module importable.
        import sys
        present = probe_in_process(Path(sys.executable))
        self.assertIn("venv", present)

    def _probe_interpreter(self, install: Path, *, test_importable: bool) -> None:
        interpreter = install / "bin" / "python3.14"
        interpreter.parent.mkdir(parents=True, exist_ok=True)
        output = '{"test": true}' if test_importable else '{"test": false}'
        interpreter.write_text(f"#!/bin/sh\nprintf '%s\\n' '{output}'\n")
        interpreter.chmod(0o755)

    def test_distribution_pruning_removes_test_and_bytecode(self):
        with tempfile.TemporaryDirectory() as temporary:
            install = Path(temporary) / "install"
            library = install / "lib/python3.14"
            test_package = library / "test"
            test_cache = test_package / "__pycache__"
            stdlib_cache = library / "json" / "__pycache__"
            test_cache.mkdir(parents=True)
            stdlib_cache.mkdir(parents=True)
            (test_package / "__init__.py").write_text("")
            (test_cache / "__init__.cpython-314.pyc").write_bytes(b"test")
            (stdlib_cache / "json.cpython-314.pyc").write_bytes(b"stdlib")
            (library / "stray.pyc").write_bytes(b"stray")
            self._probe_interpreter(install, test_importable=False)

            report = prune_distribution_payload(install)

            self.assertFalse(test_package.exists())
            self.assertFalse(verify_distribution_payload(install))
            self.assertEqual(report["removed_stdlib_dirs"], ["lib/python3.14/test"])
            self.assertEqual(report["removed_bytecode_files"], 3)
            self.assertEqual(report["removed_bytecode_cache_dirs"], 2)
            self.assertFalse(report["test_importable"])
            self.assertTrue(report["ok"])

    def test_distribution_pruning_fails_if_test_remains_importable(self):
        with tempfile.TemporaryDirectory() as temporary:
            install = Path(temporary) / "install"
            (install / "lib/python3.14/test").mkdir(parents=True)
            self._probe_interpreter(install, test_importable=True)

            with self.assertRaisesRegex(ScopeError, "remains importable"):
                prune_distribution_payload(install)


if __name__ == "__main__":
    unittest.main()
