"""Public module kernels must exercise successful native operations."""

import importlib.util
import builtins
import sys
import unittest
from pathlib import Path
from unittest import mock


@unittest.skipUnless(sys.platform == "darwin", "module memory runner requires macOS")
class MeasurementBoundaryTests(unittest.TestCase):
    def test_result_serialization_imports_after_measurement(self):
        path = Path(__file__).resolve().parents[1] / "perf_modules.py"
        spec = importlib.util.spec_from_file_location("perf_modules_boundary", path)
        kernels = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(kernels)
        imported_json = []
        original_import = builtins.__import__

        def import_module(name, *args, **kwargs):
            if name == "json":
                imported_json.append(name)
            return original_import(name, *args, **kwargs)

        def measure(*args):
            self.assertEqual(imported_json, [])
            return {"digest": "stable"}

        with mock.patch.object(builtins, "__import__", import_module), \
                mock.patch.object(kernels, "measure", measure), \
                mock.patch.object(builtins, "print"):
            self.assertEqual(kernels.main(["measure", "warnings", "--iterations", "1"]), 0)
        self.assertTrue(imported_json)


@unittest.skipUnless(sys.version_info[:2] == (3, 16) and sys.platform == "darwin",
                     "requires the staged macOS Rust interpreter")
class ModuleRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "perf_modules.py"
        spec = importlib.util.spec_from_file_location("perf_modules", path)
        cls.kernels = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.kernels)

    def test_pickle_encodes_and_decodes_supported_values_and_keeps_fallbacks(self):
        import pickle
        import _pickle_rs

        _, setup = self.kernels.k_pickle()
        run = setup()
        successes = {"dumps": 0, "loads": 0}
        original_dumps, original_loads = _pickle_rs.dumps, _pickle_rs.loads

        def dumps(*args):
            result = original_dumps(*args)
            successes["dumps"] += result is not None
            return result

        def loads(*args):
            result = original_loads(*args)
            successes["loads"] += bool(result[0])
            return result

        with mock.patch.object(_pickle_rs, "dumps", dumps), \
                mock.patch.object(_pickle_rs, "loads", loads), \
                mock.patch.object(pickle, "_cpython_dump", wraps=pickle._cpython_dump) as fallback_dump, \
                mock.patch.object(pickle, "_cpython_dumps", wraps=pickle._cpython_dumps) as fallback_dumps, \
                mock.patch.object(pickle, "_cpython_load", wraps=pickle._cpython_load) as fallback_load, \
                mock.patch.object(pickle, "_cpython_loads", wraps=pickle._cpython_loads) as fallback_loads:
            run()
        self.assertEqual(successes, {"dumps": 2, "loads": 2})
        self.assertTrue(all(call.called for call in (
            fallback_dump, fallback_dumps, fallback_load, fallback_loads)))

    def test_resources_reads_through_native_functional_operations(self):
        import _importlib_resources_rs

        _, setup = self.kernels.k_importlib_resources()
        run = setup()
        with mock.patch.object(_importlib_resources_rs, "joinpath",
                               wraps=_importlib_resources_rs.joinpath) as joinpath, \
                mock.patch.object(_importlib_resources_rs, "read_bytes",
                                  wraps=_importlib_resources_rs.read_bytes) as read_bytes, \
                mock.patch.object(_importlib_resources_rs, "read_text",
                                  wraps=_importlib_resources_rs.read_text) as read_text:
            run()
        self.assertEqual((joinpath.call_count, read_bytes.call_count, read_text.call_count),
                         (2, 1, 1))

    def test_multiprocessing_batches_pool_tasks_in_rust(self):
        import multiprocessing.pool

        _, setup = self.kernels.k_multiprocessing()
        run = setup()
        with mock.patch.object(multiprocessing.pool, "_take_chunk",
                               wraps=multiprocessing.pool._take_chunk) as take_chunk:
            run()
        self.assertGreaterEqual(take_chunk.call_count, 2)

    def test_subprocess_launches_and_reads_through_native_operations(self):
        import _subprocess_rs

        _, setup = self.kernels.k_subprocess()
        run = setup()
        with mock.patch.object(_subprocess_rs, "posix_spawn",
                               wraps=_subprocess_rs.posix_spawn) as spawn, \
                mock.patch.object(_subprocess_rs, "read",
                                  wraps=_subprocess_rs.read) as read:
            self.assertEqual(run(), (0, 65536))
        self.assertGreater(spawn.call_count, 0)
        self.assertGreater(read.call_count, 0)

    def test_tokenize_classifies_supported_lines_and_keeps_fallbacks(self):
        import _tokenize_rs

        _, setup = self.kernels.k_tokenize()
        run = setup()
        successes = []
        fallbacks = []
        original_scan = _tokenize_rs.scan_line

        def scan_line(*args):
            result = original_scan(*args)
            (fallbacks if result is None else successes).append(args[0])
            return result

        with mock.patch.object(_tokenize_rs, "scan_line", scan_line):
            output = run()
        self.assertTrue(successes, "kernel must include successful Rust classification")
        self.assertTrue(fallbacks, "kernel must retain unsupported Python syntax")
        self.assertEqual(output, (6600, "\n", 385, "2"))


if __name__ == "__main__":
    unittest.main()
