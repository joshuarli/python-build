"""Observable contracts for the native counting helper."""
import collections
import importlib
import sys
import unittest
import weakref
from unittest.mock import patch

import _collections
import _collections_rs as native


class SlotExportTests(unittest.TestCase):
    def test_metadata_counting_and_argument_errors(self):
        self.assertEqual(native.__name__, "_collections_rs")
        self.assertEqual(native.__doc__, "Rust counting operations for collections.")
        self.assertIs(native.subtract_iterable.__self__, native)
        self.assertEqual(native.subtract_iterable.__doc__,
                         "Subtract one from the mapped count for each iterable element.")
        values = ["a", "b", "a", "c", "b", "a"]
        counted = {}
        _collections._count_elements(counted, values)
        actual = dict(counted)
        self.assertIsNone(native.subtract_iterable(actual, iter(values), actual.get))
        self.assertEqual(actual, {key: 0 for key in counted})
        empty = {}
        self.assertIsNone(native.subtract_iterable(empty, (), empty.get))
        for args in ((), ({},), ({}, ()), ({}, (), {}.get, None)):
            with self.assertRaisesRegex(TypeError, "^subtract_iterable requires a mapping, iterable, and bound get method$"):
                native.subtract_iterable(*args)

    def test_public_dispatch_monkeypatch_fallback_and_native_types(self):
        original = native.subtract_iterable
        calls = []
        identities = (_collections.deque, _collections.defaultdict, _collections.OrderedDict)
        def observe(mapping, iterable, get):
            calls.append(mapping)
            return original(mapping, iterable, get)
        try:
            native.subtract_iterable = observe
            counter = collections.Counter(a=3)
            counter.subtract(["a", "a", "b"])
            self.assertEqual(counter, {"a": 1, "b": -1})
            self.assertEqual(calls, [counter])
            counter.subtract({"a": 2})
            self.assertEqual(len(calls), 1)
        finally:
            native.subtract_iterable = original
        with patch.dict(sys.modules, {"_collections_rs": None}):
            fallback = collections.Counter(a=3)
            fallback.subtract(["a", "a", "b"])
            self.assertEqual(fallback, {"a": 1, "b": -1})
        self.assertEqual(identities,
                         (_collections.deque, _collections.defaultdict, _collections.OrderedDict))
        self.assertIs(collections.deque, _collections.deque)
        self.assertIs(collections.defaultdict, _collections.defaultdict)
        self.assertIs(collections.OrderedDict, _collections.OrderedDict)

    def test_error_identity_reentry_and_temporary_reference_release(self):
        for boundary in ("iterate", "get", "subtract", "set"):
            sentinel = RuntimeError(boundary)
            refs = []
            class Key:
                pass
            class Result:
                pass
            class Value:
                def __sub__(self, one):
                    self_test.assertEqual(one, 1)
                    if boundary == "subtract":
                        raise sentinel
                    result = Result()
                    refs.append(weakref.ref(result))
                    return result
            class Iterable:
                def __iter__(self):
                    if boundary == "iterate":
                        raise sentinel
                    key = Key()
                    refs.append(weakref.ref(key))
                    yield key
            class Mapping:
                def get(self, key, zero):
                    self_test.assertEqual(zero, 0)
                    if boundary == "get":
                        raise sentinel
                    value = Value()
                    refs.append(weakref.ref(value))
                    return value
                def __setitem__(self, key, value):
                    if boundary == "set":
                        raise sentinel
                    raise AssertionError("unexpected successful store")
            self_test = self
            mapping = Mapping()
            with self.assertRaises(RuntimeError) as caught:
                native.subtract_iterable(mapping, Iterable(), mapping.get)
            self.assertIs(caught.exception, sentinel)
            self.assertTrue(all(reference() is None for reference in refs))
        nested = {}
        class ReentrantValue:
            def __sub__(self, one):
                native.subtract_iterable(nested, ("inner",), nested.get)
                return 4
        mapping = {"outer": ReentrantValue()}
        native.subtract_iterable(mapping, ("outer",), mapping.get)
        self.assertEqual(mapping, {"outer": 4})
        self.assertEqual(nested, {"inner": -1})

    def test_reload_and_thread_transfer_preserve_retained_callable(self):
        from concurrent.futures import ThreadPoolExecutor
        retained = native.subtract_iterable
        self.assertIs(importlib.reload(native), native)
        self.assertIs(native.subtract_iterable, retained)
        def count():
            mapping = {"a": 4}
            self.assertIsNone(retained(mapping, ("a", "b", "a"), mapping.get))
            return mapping
        with ThreadPoolExecutor(max_workers=1) as executor:
            self.assertEqual(executor.submit(count).result(timeout=10), {"a": 2, "b": -1})
        self.assertIs(retained.__self__, native)


if __name__ == "__main__":
    unittest.main()
