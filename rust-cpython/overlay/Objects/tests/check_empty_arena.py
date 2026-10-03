"""Run with the separately compiled C observer in a fresh GIL interpreter."""
import importlib.util
import pathlib
import sys
import sysconfig
import threading
import unittest

OBSERVER = pathlib.Path(sys.argv.pop(1)).resolve()

class EmptyArenaRelease(unittest.TestCase):
    def test_live_block_retention_final_release_and_reacquisition(self):
        self.assertFalse(sysconfig.get_config_var("Py_GIL_DISABLED"))
        self.assertEqual(threading.active_count(), 1)
        spec = importlib.util.spec_from_file_location("_empty_arena_fixture", OBSERVER)
        observer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(observer)
        self.assertGreater(observer.exercise(), 3)

if __name__ == "__main__":
    unittest.main()
