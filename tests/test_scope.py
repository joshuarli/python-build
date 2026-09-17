"""The GUI exclusion applies to acquisition as well as compilation."""
import unittest
from pathlib import Path

from buildsys.deporder import DEPENDENCY_ORDER
from buildsys.inputs import load_lock


class ScopeTests(unittest.TestCase):
    def test_gui_closure_is_not_a_build_or_acquisition_input(self):
        excluded = {"tcl", "tk", "libx11", "libxau", "libxcb", "xcb-proto",
                    "xorgproto", "xtrans", "util-macros", "libpthread-stubs"}
        self.assertFalse(excluded.intersection(DEPENDENCY_ORDER))
        lock = Path(__file__).resolve().parents[1] / "sources.lock.json"
        self.assertFalse(excluded.intersection(item.name for item in load_lock(lock)))
