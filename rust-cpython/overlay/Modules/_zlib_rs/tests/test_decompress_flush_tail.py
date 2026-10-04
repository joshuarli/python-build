"""EOF flush preserves trailing input retained after limited decompression."""
import unittest
import zlib


class DecompressFlushTailTests(unittest.TestCase):
    def test_limited_decode_flush_retains_trailing_compressed_bytes(self):
        payload = b"abcdef"
        trailer = b"trailing compressed bytes"
        for wbits in (15, -15):
            for trailing in (trailer, b""):
                with self.subTest(wbits=wbits, trailing=trailing):
                    packed = zlib.compress(payload, 0, wbits=wbits)
                    decoder = zlib.decompressobj(wbits)
                    self.assertEqual(decoder.decompress(packed + trailing, 1), b"a")
                    self.assertFalse(decoder.eof)
                    self.assertTrue(decoder.unconsumed_tail)
                    self.assertEqual(decoder.flush(), b"bcdef")
                    self.assertTrue(decoder.eof)
                    self.assertEqual(decoder.unused_data, trailing)
                    self.assertEqual(decoder.unconsumed_tail, trailing)
                    self.assertEqual(decoder.flush(), b"")
                    self.assertEqual(decoder.unconsumed_tail, trailing)
                    self.assertEqual(decoder.unused_data, trailing)


if __name__ == "__main__":
    unittest.main()
