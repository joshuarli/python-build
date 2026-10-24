from __future__ import annotations

import array
import ssl
import unittest


class MemoryBIOContract(unittest.TestCase):
    def test_buffer_size_and_rejected_write_preserve_contents(self):
        data = array.array("I", [1, 2, 3])
        view = memoryview(data)
        bio = ssl.MemoryBIO()
        self.assertEqual(bio.write(view), view.nbytes)
        with self.assertRaises(BufferError):
            bio.write(view[::2])
        self.assertEqual(bio.read(), view.tobytes())

    def test_invalid_buffers_preserve_contents(self):
        bio = ssl.MemoryBIO()
        bio.write(b"retained")
        for value in (None, "", False, 0, 1):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    bio.write(value)
        self.assertEqual(bio.read(), b"retained")

    def test_read_integer_bounds_and_positional_arguments(self):
        class Size:
            def __index__(self):
                return 2

        bio = ssl.MemoryBIO()
        bio.write(b"abcdef")
        for value in (-(1 << 31) - 1, 1 << 31):
            with self.subTest(value=value):
                with self.assertRaises(OverflowError):
                    bio.read(value)
        with self.assertRaises(TypeError):
            bio.read(size=1)
        with self.assertRaises(TypeError):
            bio.write(data=b"discarded")
        self.assertEqual(bio.read(Size()), b"ab")
        self.assertEqual(bio.read(-(1 << 31)), b"cdef")

    def test_eof_rejects_empty_writes_after_buffer_validation(self):
        bio = ssl.MemoryBIO()
        bio.write(b"retained")
        bio.write_eof()
        with self.assertRaises(ssl.SSLError) as failure:
            bio.write(b"")
        self.assertEqual(failure.exception.args, ("cannot write() after write_eof()",))
        with self.assertRaises(TypeError):
            bio.write(None)
        self.assertFalse(bio.eof)
        self.assertEqual(bio.read(), b"retained")
        self.assertTrue(bio.eof)


if __name__ == "__main__":
    unittest.main()
