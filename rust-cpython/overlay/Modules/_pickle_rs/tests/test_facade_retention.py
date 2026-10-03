"""Check the pickle facade's dispatch boundaries without retained helper functions."""

import inspect
import io
import pickle
import types
import unittest
from unittest import mock
from pathlib import Path

import _pickle_rs


class FacadeRetentionTests(unittest.TestCase):
    def test_public_functions_keep_signatures_documentation_and_module(self):
        signatures = {
            "dump": "(obj, file, protocol=None, *, fix_imports=True, buffer_callback=None)",
            "dumps": "(obj, protocol=None, *, fix_imports=True, buffer_callback=None)",
            "load": "(file, *, fix_imports=True, encoding='ASCII', errors='strict', buffers=None)",
            "loads": "(s, /, *, fix_imports=True, encoding='ASCII', errors='strict', buffers=None)",
        }
        for name, signature in signatures.items():
            with self.subTest(name=name):
                function = getattr(pickle, name)
                original = getattr(pickle, "_cpython_" + name)
                self.assertIs(type(function), types.FunctionType)
                self.assertEqual(str(inspect.signature(function)), signature)
                self.assertEqual(function.__doc__, original.__doc__)
                self.assertEqual(function.__module__, original.__module__)
        for name in ("_rust_pickle_protocol", "_rust_pickle_load_options", "_rust_loads"):
            self.assertNotIn(name, vars(pickle))
            for public in signatures:
                self.assertNotIn(name, getattr(pickle, public).__code__.co_names)

    def test_native_graph_still_reaches_rust_for_all_four_public_functions(self):
        value = {"items": [None, True, False, -7, 42, 1.25, b"native", "rust ü"]}
        with mock.patch.object(_pickle_rs, "dumps", wraps=_pickle_rs.dumps) as encode, \
                mock.patch.object(_pickle_rs, "loads", wraps=_pickle_rs.loads) as decode:
            encoded = pickle.dumps(value)
            self.assertEqual(pickle.loads(encoded), value)
            stream = io.BytesIO()
            pickle.dump(value, stream)
            stream.seek(0)
            self.assertEqual(pickle.load(stream), value)
        self.assertEqual(encode.call_count, 2)
        self.assertEqual(decode.call_count, 2)

    def test_fallback_receives_existing_normalized_arguments(self):
        class Protocol(int):
            pass

        value = {"x": 1}
        protocol = Protocol(4)
        stream = io.BytesIO()
        with mock.patch.object(_pickle_rs, "dumps", wraps=_pickle_rs.dumps) as encode, \
                mock.patch.object(pickle, "_cpython_dump", wraps=pickle._cpython_dump) as dump, \
                mock.patch.object(pickle, "_cpython_dumps", wraps=pickle._cpython_dumps) as dumps:
            pickle.dump(value, stream, protocol)
            encoded = pickle.dumps(value, protocol)
        encode.assert_not_called()
        dump.assert_called_once_with(value, stream, protocol, fix_imports=True, buffer_callback=None)
        dumps.assert_called_once_with(value, protocol, fix_imports=True, buffer_callback=None)
        with mock.patch.object(_pickle_rs, "loads", wraps=_pickle_rs.loads) as decode, \
                mock.patch.object(pickle, "_cpython_loads", wraps=pickle._cpython_loads) as loads:
            self.assertEqual(pickle.loads(bytearray(encoded)), value)
        decode.assert_not_called()
        loads.assert_called_once_with(bytearray(encoded), fix_imports=True, encoding="ASCII", errors="strict", buffers=None)

    def test_nondefault_load_options_keep_complete_unpickler(self):
        class Encoding(str):
            pass

        value = {"x": 1}
        encoded = _pickle_rs.dumps(value, 5)
        for options in ({"encoding": Encoding("ASCII")}, {"buffers": []}, {"fix_imports": 1}):
            with self.subTest(options=options), \
                    mock.patch.object(_pickle_rs, "loads", wraps=_pickle_rs.loads) as decode:
                self.assertEqual(pickle.loads(encoded, **options), value)
                self.assertEqual(pickle.load(io.BytesIO(encoded), **options), value)
                decode.assert_not_called()

    def test_closed_stream_and_unicode_input_keep_fallback_errors(self):
        with self.assertRaisesRegex(TypeError, "bytes-like object"):
            pickle.loads("not bytes")
        stream = io.BytesIO()
        stream.close()
        with self.assertRaisesRegex(ValueError, "closed file"):
            pickle.load(stream)

    def test_helper_removed_during_stream_read_preserves_fallback(self):
        value = {"x": 1}
        encoded = _pickle_rs.dumps(value, 5)
        original_bytes_io = io.BytesIO

        class Stream(original_bytes_io):
            def getvalue(self):
                pickle._pickle_rs = None
                return super().getvalue()

        helper = pickle._pickle_rs
        try:
            with mock.patch.object(io, "BytesIO", Stream), \
                    mock.patch.object(pickle, "_cpython_load", wraps=pickle._cpython_load) as load:
                stream = Stream(encoded)
                self.assertEqual(pickle.load(stream), value)
                load.assert_called_once_with(stream, fix_imports=True, encoding="ASCII", errors="strict", buffers=None)
        finally:
            pickle._pickle_rs = helper


    def test_source_upgrade_keeps_callable_helpers_for_held_old_functions(self):
        baseline_path = Path(__file__).with_name("legacy_facade_snapshot.py")
        candidate_path = Path(pickle.__file__)
        module = types.ModuleType("pickle_upgrade_fixture")
        module.__dict__.update(vars(pickle))
        namespace = vars(module)
        exec(compile(baseline_path.read_bytes(), str(baseline_path), "exec"), namespace)
        names = ("_rust_pickle_protocol", "_rust_pickle_load_options", "_rust_loads")
        legacy = {name: namespace[name] for name in names}
        held = {name: namespace[name] for name in ("dump", "dumps", "load", "loads")}
        exec(compile(candidate_path.read_bytes(), str(candidate_path), "exec"), namespace)
        for name in names:
            self.assertIs(namespace[name], legacy[name])
            self.assertTrue(callable(namespace[name]))
        for name, function in held.items():
            self.assertIs(function.__globals__, namespace)
            self.assertIsNot(namespace[name], function)
        value = {"items": [None, True, -7, b"native", "rust ü"]}
        with mock.patch.object(_pickle_rs, "dumps", wraps=_pickle_rs.dumps) as encode, \
                mock.patch.object(_pickle_rs, "loads", wraps=_pickle_rs.loads) as decode:
            encoded = held["dumps"](value)
            self.assertEqual(held["loads"](encoded), value)
            stream = io.BytesIO()
            held["dump"](value, stream)
            stream.seek(0)
            self.assertEqual(held["load"](stream), value)
        self.assertEqual(encode.call_count, 2)
        self.assertEqual(decode.call_count, 2)


if __name__ == "__main__":
    unittest.main()
