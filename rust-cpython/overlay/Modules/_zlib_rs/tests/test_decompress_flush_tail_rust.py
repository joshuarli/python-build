"""Rust capsule copies retain EOF trailers after limited decompression."""
import unittest

import _zlib_rs as native


class RustDecompressFlushTailTests(unittest.TestCase):
    def test_capsule_and_copy_retain_trailer_after_flush(self):
        payload = b"abcdef"
        trailer = b"trailing compressed bytes"
        for wbits in (15, -15):
            with self.subTest(wbits=wbits):
                packed = native.compress_once(payload, 0, wbits)
                capsule = native.decompressor(wbits)
                self.assertEqual(native.decompress(capsule, packed + trailer, 1), b"a")
                duplicate = native.decompressor_copy(capsule)
                for state in (capsule, duplicate):
                    self.assertEqual(native.decompressor_flush(state, 1), b"bcdef")
                    self.assertTrue(native.eof(state))
                    self.assertEqual(native.unused_data(state), trailer)
                    self.assertEqual(native.unconsumed_tail(state), trailer)


if __name__ == "__main__":
    unittest.main()
