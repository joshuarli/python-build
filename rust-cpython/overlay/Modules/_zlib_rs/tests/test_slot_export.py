"""Method ownership, stream lifetimes, and public zlib dispatch contracts."""
import copy
import importlib
import unittest

import _zlib_rs as native
import zlib

NAMES = ("compress_once", "decompress_once", "compressor", "compress", "flush",
         "compressor_copy", "decompressor", "decompress", "eof", "unused_data",
         "unconsumed_tail", "decompressor_flush", "decompressor_copy")


class SlotExportTests(unittest.TestCase):
    def test_methods_reload_and_errors(self):
        methods = tuple(getattr(native, name) for name in NAMES)
        for name, method in zip(NAMES, methods):
            self.assertEqual(method.__name__, name)
            self.assertEqual(method.__module__, "_zlib_rs")
            self.assertIs(method.__self__, native)
            self.assertIsInstance(method.__doc__, str)
            with self.assertRaises(TypeError):
                method()
            with self.assertRaises(TypeError):
                method(unexpected=1)
        self.assertEqual(native.__doc__, "Rust DEFLATE codecs for zlib.")
        self.assertIs(importlib.reload(native), native)
        self.assertEqual(tuple(getattr(native, name) for name in NAMES), methods)
        for wbits in (15, -15):
            payload = bytearray(b"retained export " * 300)
            packed = methods[0](payload, 0, wbits)
            payload.extend(b"released buffer")
            self.assertEqual(methods[1](packed, wbits), b"retained export " * 300)
        with self.assertRaises(ValueError):
            native.compress_once(b"data", 10, 15)
        with self.assertRaises(ValueError):
            native.decompress_once(b"invalid stream", 15)
        with self.assertRaises(ValueError):
            native.eof(native.compressor(0, 15))

    def test_public_stream_copies_tail_and_fallback(self):
        for wbits in (15, -15):
            compressor = zlib.compressobj(0, wbits=wbits)
            self.assertEqual(type(compressor._state).__name__, "PyCapsule")
            prefix = compressor.compress(b"prefix")
            duplicate = copy.copy(compressor)
            suffix = compressor.compress(b"suffix") + compressor.flush()
            self.assertEqual(suffix, duplicate.compress(b"suffix") + duplicate.flush())
            decoder = zlib.decompressobj(wbits)
            packed = prefix + suffix
            first = decoder.decompress(packed, 3)
            self.assertTrue(decoder.unconsumed_tail)
            twin = copy.deepcopy(decoder)
            tail = decoder.unconsumed_tail
            self.assertEqual(first + decoder.decompress(tail) + decoder.flush(), b"prefixsuffix")
            self.assertEqual(first + twin.decompress(tail) + twin.flush(), b"prefixsuffix")
            finished = zlib.decompressobj(wbits)
            self.assertEqual(finished.decompress(packed + b"trailer"), b"prefixsuffix")
            self.assertTrue(finished.eof)
            self.assertEqual(finished.unused_data, b"trailer")
            self.assertEqual(type(compressor).__name__, "Compress")
            self.assertEqual(type(decoder).__name__, "Decompress")
        fallback = zlib.compressobj(wbits=31)
        self.assertFalse(hasattr(fallback, "_state"))
        gzip = fallback.compress(b"gzip fallback") + fallback.flush()
        self.assertEqual(zlib.decompress(gzip, 31), b"gzip fallback")

    def test_public_monkeypatch_dispatch_and_error_translation(self):
        original = native.compress_once
        calls = []
        def replacement(*args):
            calls.append(args)
            return b"replacement"
        try:
            native.compress_once = replacement
            self.assertEqual(zlib.compress(b"input", 0), b"replacement")
            self.assertEqual(calls, [(b"input", 0, 15)])
            def fail(*args):
                raise ValueError("Error -3 while compressing data: sentinel")
            native.compress_once = fail
            with self.assertRaises(zlib.error) as raised:
                zlib.compress(b"input")
            self.assertEqual(str(raised.exception), "Error -3 while compressing data: sentinel")
        finally:
            native.compress_once = original
        self.assertEqual(zlib.decompress(zlib.compress(b"restored", 0)), b"restored")


if __name__ == "__main__":
    unittest.main()
