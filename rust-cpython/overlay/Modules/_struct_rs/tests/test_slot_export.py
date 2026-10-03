"""Method ownership and public dispatch across immutable module metadata."""
import importlib
import struct
import sys
import threading
import unittest

import _struct
import _struct_rs as native


NAMES = ("pack", "unpack", "unpack_from")
DOCS = ("Pack supported standard binary records",
        "Unpack supported standard binary records",
        "Unpack a standard binary record at an offset")


class SlotExportTests(unittest.TestCase):
    def test_method_metadata_results_and_unsupported_sentinel(self):
        self.assertEqual(native.__doc__,
                         "Rust implementation of standard binary record packing")
        for name, doc in zip(NAMES, DOCS):
            method = getattr(native, name)
            self.assertEqual(method.__name__, name)
            self.assertEqual(method.__module__, "_struct_rs")
            self.assertEqual(method.__doc__, doc)
            self.assertIs(method.__self__, native)
            self.assertIs(method(), False)
            with self.assertRaises(TypeError):
                method(unexpected=1)
        payload = b"\x04\x03\x02\x01"
        self.assertEqual(native.pack("<I", (0x01020304,)), payload)
        self.assertEqual(native.unpack("<I", payload), (0x01020304,))
        self.assertEqual(native.unpack_from("<I", b"x" + payload, 1), (0x01020304,))
        self.assertIs(native.pack("@I", (1,)), False)
        self.assertIs(native.pack("<B", (256,)), False)
        self.assertIs(native.unpack("<I", b"short"), False)
        self.assertIs(native.unpack_from("<I", payload, -1), False)

    def test_public_native_types_dispatch_and_fallback_errors(self):
        self.assertIs(struct.Struct, _struct.Struct)
        self.assertIs(struct.error, _struct.error)
        original = {name: getattr(native, name) for name in NAMES}
        calls = []

        def wrap(name):
            def call(*args):
                calls.append(name)
                return original[name](*args)
            return call

        try:
            for name in NAMES:
                setattr(native, name, wrap(name))
            payload = struct.pack("<I", 0x01020304)
            self.assertEqual(struct.unpack("<I", payload), (0x01020304,))
            self.assertEqual(struct.unpack_from("<I", b"x" + payload, 1), (0x01020304,))
            self.assertEqual(set(calls), set(NAMES))
            native.pack = lambda *args: False
            self.assertEqual(struct.pack("<I", 1), b"\x01\x00\x00\x00")
            with self.assertRaises(struct.error):
                struct.pack("<B", 256)
            with self.assertRaises(struct.error):
                struct.unpack("<I", b"x")
        finally:
            for name, method in original.items():
                setattr(native, name, method)

    def test_reload_and_worker_keep_retained_methods_owned(self):
        methods = tuple(getattr(native, name) for name in NAMES)
        self.assertIs(importlib.reload(native), native)
        self.assertEqual(tuple(getattr(native, name) for name in NAMES), methods)
        baseline = sys.getrefcount(native)
        failures = []

        def worker():
            try:
                self.assertEqual(methods[0]("<I", (1,)), b"\x01\x00\x00\x00")
                self.assertEqual(methods[1]("<I", b"\x01\x00\x00\x00"), (1,))
                self.assertTrue(all(method.__self__ is native for method in methods))
            except BaseException as error:
                failures.append((type(error).__name__, str(error)))

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(10)
        self.assertFalse(thread.is_alive(), "struct worker did not finish")
        self.assertEqual(failures, [])
        self.assertEqual(sys.getrefcount(native), baseline)

    def test_exporter_release_and_native_format_fallback_remain_unchanged(self):
        buffer = bytearray(b"\x01\x00\x00\x00")
        self.assertEqual(native.unpack("<I", buffer), (1,))
        self.assertIs(native.unpack_from("<I", buffer, -1), False)
        buffer.extend(b"x")
        self.assertEqual(len(buffer), 5)
        self.assertEqual(struct.unpack("@I", struct.pack("@I", 17)), (17,))
        self.assertEqual(struct.unpack("<p", struct.pack("<p", b"x")), (b"",))


if __name__ == "__main__":
    unittest.main()
