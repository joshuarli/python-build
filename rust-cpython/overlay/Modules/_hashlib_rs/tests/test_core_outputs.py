"""Native digest outputs and heap-type ownership survive bounded stack writes."""

import _hashlib
import _hashlib_rs
import gc
import hashlib
import sys
import unittest


ALGORITHMS = ("md5", "sha1", "sha224", "sha256", "sha384", "sha512")


class CoreHashOutputTests(unittest.TestCase):
    def test_digest_lengths_block_boundaries_and_retained_outputs(self):
        payload = bytes(range(256)) + b"last"
        for name in ALGORITHMS:
            for length in (0, 63, 64, 65, 127, 128, 129, 257):
                with self.subTest(name=name, length=length):
                    data = bytearray(payload[:length])
                    context = getattr(hashlib, name)(data, usedforsecurity=False)
                    native = _hashlib.new(name, data, usedforsecurity=False)
                    self.assertEqual(type(context).__module__, "_hashlib_rs")
                    self.assertEqual(context.name, native.name)
                    self.assertEqual(context.digest_size, native.digest_size)
                    self.assertEqual(context.block_size, native.block_size)
                    retained = context.digest(), context.hexdigest()
                    expected = native.digest(), native.hexdigest()
                    data[:] = b"changed"
                    context.update(memoryview(payload))
                    native.update(memoryview(payload))
                    copied = context.copy()
                    self.assertEqual(context.digest(), native.digest())
                    self.assertEqual(copied.digest(), native.digest())
                    self.assertEqual(context.hexdigest(), native.hexdigest())
                    self.assertEqual(len(context.digest()), context.digest_size)
                    self.assertEqual(len(context.hexdigest()), context.digest_size * 2)
                    self.assertEqual(retained, expected)

    def test_direct_native_constructor_errors_are_preserved(self):
        for args in ((), ("sha256",), ("sha256", b"", None)):
            with self.subTest(args=args):
                with self.assertRaisesRegex(TypeError, "^invalid number of arguments$"):
                    _hashlib_rs.new(*args)
        for name in ("", "SHA256", "sha256\0", "\u2603"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "^unsupported hash algorithm$"):
                    _hashlib_rs.new(name, b"")
        with self.assertRaises(TypeError):
            _hashlib_rs.new(b"sha256", b"")
        with self.assertRaises(UnicodeEncodeError):
            _hashlib_rs.new("\ud800", b"")
        with self.assertRaises(TypeError):
            _hashlib_rs.new("sha256", "text")
        with self.assertRaises(BufferError):
            _hashlib_rs.new("sha256", memoryview(b"abcdef")[::2])

    def test_hash_layout_readonly_fields_and_copy_type_reference_release(self):
        hash_type = _hashlib_rs.HASH
        self.assertEqual(hash_type.__basicsize__, 24)
        self.assertTrue(hash_type.__flags__ & (1 << 9))
        self.assertTrue(hash_type.__flags__ & (1 << 8))
        with self.assertRaises(TypeError):
            hash_type()
        gc.collect()
        baseline = sys.getrefcount(hash_type)
        context = _hashlib_rs.new("sha512", b"payload")
        copied = context.copy()
        self.assertEqual(sys.getrefcount(hash_type), baseline + 2)
        self.assertRegex(repr(context), r"^<sha512 HASH object @ 0x[0-9a-f]+>$")
        with self.assertRaises(TypeError):
            hash(context)
        for name in ("name", "digest_size", "block_size"):
            with self.subTest(name=name):
                with self.assertRaises(AttributeError):
                    setattr(context, name, 0)
        del context, copied
        gc.collect()
        self.assertEqual(sys.getrefcount(hash_type), baseline)


if __name__ == "__main__":
    unittest.main()
