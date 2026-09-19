"""Scope exclusions apply to acquisition as well as compilation."""
import unittest
from pathlib import Path

from buildsys.deporder import (
    DEPENDENCY_ORDER, LINUX_DEPENDENCY_ORDER, MACOS_DEPENDENCY_ORDER,
)
from buildsys.inputs import load_lock

# Tcl/Tk and everything that exists solely to serve its GUI are outside the
# product on every family (plan scope decision).
GUI_CLOSURE = {"tcl", "tk", "libx11", "libxau", "libxcb", "xcb-proto",
               "xorgproto", "xtrans", "util-macros", "libpthread-stubs"}

# Libraries macOS supplies itself; bundling a second copy would shadow the
# platform's and make the artifact less portable, not more (plan Section 5.2).
MACOS_PLATFORM_PROVIDED = {"zlib", "expat", "libedit", "libuuid", "bdb"}


class ScopeTests(unittest.TestCase):
    def test_gui_closure_is_not_a_build_or_acquisition_input(self):
        self.assertFalse(GUI_CLOSURE.intersection(LINUX_DEPENDENCY_ORDER))
        self.assertFalse(GUI_CLOSURE.intersection(MACOS_DEPENDENCY_ORDER))
        lock = Path(__file__).resolve().parents[1] / "sources.lock.json"
        self.assertFalse(GUI_CLOSURE.intersection(item.name for item in load_lock(lock)))

    def test_macos_does_not_build_libraries_the_platform_provides(self):
        self.assertFalse(MACOS_PLATFORM_PROVIDED.intersection(MACOS_DEPENDENCY_ORDER))

    def test_macos_still_builds_its_private_dependency_set(self):
        for name in ("openssl", "sqlite", "libffi", "bzip2", "xz", "zstd",
                     "mpdecimal", "ncurses"):
            self.assertIn(name, MACOS_DEPENDENCY_ORDER)

    def test_linux_order_is_unchanged_and_remains_the_default(self):
        # The frozen Linux targets' order is evidence-bearing: it must not
        # drift because a second family was added.
        self.assertIs(DEPENDENCY_ORDER, LINUX_DEPENDENCY_ORDER)
        self.assertIn("bdb", LINUX_DEPENDENCY_ORDER)
        self.assertIn("libuuid", LINUX_DEPENDENCY_ORDER)
        self.assertIn("pkgconf", LINUX_DEPENDENCY_ORDER)

    def test_no_order_contains_duplicates(self):
        for order in (LINUX_DEPENDENCY_ORDER, MACOS_DEPENDENCY_ORDER):
            self.assertEqual(len(order), len(set(order)))


if __name__ == "__main__":
    unittest.main()
