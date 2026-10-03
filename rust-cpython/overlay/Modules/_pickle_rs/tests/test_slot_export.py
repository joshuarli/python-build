"""Observable pickle codec, dispatch, and module-lifetime contracts."""
import importlib
import io
import pickle
import threading
import unittest

import _pickle
import _pickle_rs as native


VALUE = {"name": "\u03bb", "items": [None, True, -17, 1.25, b"payload"]}


class PickleSlotExportTests(unittest.TestCase):
    def test_private_metadata_roundtrip_consumption_and_unsupported_status(self):
        self.assertEqual(native.__doc__, "Rust pickle codec for common builtin object graphs")
        for name, doc in (("dumps", "Serialize a supported builtin pickle graph"),
                          ("loads", "Deserialize a supported builtin pickle graph")):
            method = getattr(native, name)
            self.assertEqual(method.__name__, name)
            self.assertEqual(method.__module__, "_pickle_rs")
            self.assertIs(method.__self__, native)
            self.assertEqual(method.__doc__, doc)
            with self.assertRaises(TypeError):
                method()
            with self.assertRaises(TypeError):
                method(unexpected=1)
        for protocol in (None, -1, 3, 4, 5):
            encoded = native.dumps(VALUE, protocol)
            self.assertIs(type(encoded), bytes)
            self.assertEqual(_pickle.loads(encoded), VALUE)
            self.assertEqual(native.loads(encoded + b"trailing"), (True, VALUE, len(encoded)))
        self.assertIsNone(native.dumps(VALUE, 2))
        self.assertIsNone(native.dumps((1, 2), 5))
        self.assertEqual(native.loads(bytearray(b"not pickle")), (False, None, 0))
        self.assertEqual(native.loads(b"not pickle"), (False, None, 0))
        with self.assertRaises(TypeError):
            native.dumps(VALUE, 5, None)
        with self.assertRaises(TypeError):
            native.loads(b"", None)

    def test_four_public_routes_resolve_mutable_native_methods(self):
        original = {name: getattr(native, name) for name in ("dumps", "loads")}
        calls = []

        def wrap(name):
            def call(*args):
                calls.append(name)
                return original[name](*args)
            return call

        try:
            for name in original:
                setattr(native, name, wrap(name))
            encoded = pickle.dumps(VALUE, protocol=5)
            stream = io.BytesIO()
            self.assertIsNone(pickle.dump(VALUE, stream, protocol=5))
            self.assertEqual(pickle.loads(encoded), VALUE)
            stream.seek(0)
            self.assertEqual(pickle.load(stream), VALUE)
            self.assertEqual(stream.tell(), len(stream.getvalue()))
            self.assertEqual(calls, ["dumps", "dumps", "loads", "loads"])
        finally:
            for name, method in original.items():
                setattr(native, name, method)

    def test_native_public_types_memo_aliases_errors_and_missing_helper_fallback(self):
        for name in ("Pickler", "Unpickler", "PickleError", "UnpicklingError"):
            self.assertIs(getattr(pickle, name), getattr(_pickle, name))
        shared = []
        value = [shared, shared]
        stream = io.BytesIO()
        pickler = pickle.Pickler(stream, protocol=5)
        pickler.dump(value)
        self.assertTrue(pickler.memo.copy())
        decoded = pickle.loads(stream.getvalue())
        self.assertIs(decoded[0], decoded[1])
        saved = pickle._pickle_rs
        try:
            pickle._pickle_rs = None
            self.assertEqual(pickle.loads(pickle.dumps(VALUE, protocol=5)), VALUE)
            stream = io.BytesIO()
            pickle.dump(VALUE, stream, protocol=2)
            stream.seek(0)
            self.assertEqual(pickle.load(stream), VALUE)
        finally:
            pickle._pickle_rs = saved
        self.assertEqual(pickle.loads(pickle.dumps((1, 2), protocol=5)), (1, 2))
        with self.assertRaises(pickle.UnpicklingError):
            pickle.loads(b"not pickle")

    def test_reload_and_thread_transfer_keep_retained_methods_live(self):
        methods = (native.dumps, native.loads)
        self.assertIs(importlib.reload(native), native)
        self.assertIs(native.dumps, methods[0])
        self.assertIs(native.loads, methods[1])
        failures = []

        def worker():
            try:
                encoded = methods[0](VALUE, 5)
                self.assertEqual(methods[1](encoded), (True, VALUE, len(encoded)))
                self.assertTrue(all(method.__self__ is native for method in methods))
            except BaseException as error:
                failures.append((type(error).__name__, str(error)))

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(10)
        self.assertFalse(thread.is_alive(), "pickle worker did not finish")
        self.assertEqual(failures, [])
        self.assertEqual(pickle.loads(methods[0](VALUE, 5)), VALUE)


if __name__ == "__main__":
    unittest.main()
