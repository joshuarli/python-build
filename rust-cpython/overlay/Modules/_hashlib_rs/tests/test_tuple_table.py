"""Compact digest dispatch preserves native validation and Rust coverage."""

import _blake2
import _hashlib
import hashlib
import unittest


ALGORITHMS = ("md5", "sha1", "sha224", "sha256", "sha384", "sha512")


class UnhashableName(str):
    __hash__ = None


class HashlibTupleTableTests(unittest.TestCase):
    def test_named_and_alias_constructors_preserve_rust_digest_routing(self):
        self.assertIs(type(hashlib._rust_hash_algorithms), tuple)
        self.assertEqual(hashlib._rust_hash_algorithms, ALGORITHMS)
        for name in ALGORITHMS:
            with self.subTest(name=name):
                native = _hashlib.new(name, b"prefix", usedforsecurity=False)
                native.update(b"suffix")
                contexts = [getattr(hashlib, name)(b"prefix", usedforsecurity=False),
                            hashlib.new(name, b"prefix", usedforsecurity=False),
                            hashlib.new(name.upper(), b"prefix", usedforsecurity=False)]
                for context in contexts:
                    self.assertEqual(type(context).__module__, "_hashlib_rs")
                    self.assertEqual(context.name, native.name)
                    context.update(b"suffix")
                    self.assertEqual(context.digest(), native.digest())
                    self.assertEqual(context.hexdigest(), native.hexdigest())

    def test_raw_name_hashing_and_native_argument_errors_are_preserved(self):
        for name in ([], {}, UnhashableName("sha256")):
            with self.subTest(name=type(name).__name__):
                with self.assertRaisesRegex(TypeError, "unhashable type"):
                    hashlib.new(name)
        for name in ALGORITHMS:
            with self.subTest(name=name):
                constructor = getattr(hashlib, name)
                with self.assertRaises(TypeError):
                    constructor("text")
                with self.assertRaises(TypeError):
                    hashlib.new(name, "text")
                with self.assertRaises(TypeError):
                    constructor(unexpected=True)
                with self.assertRaises(TypeError):
                    hashlib.new(name, unexpected=True)

    def test_blake2_and_unported_digest_backends_keep_native_behavior(self):
        payload = b"payload"
        native = _blake2.blake2b(payload, key=b"key", digest_size=32)
        public = hashlib.new("blake2b", payload, key=b"key", digest_size=32)
        self.assertEqual(type(public).__module__, type(native).__module__)
        self.assertEqual(public.digest(), native.digest())
        native = _hashlib.new("sha3_256", payload, usedforsecurity=False)
        public = hashlib.new("sha3_256", payload, usedforsecurity=False)
        self.assertEqual(type(public).__module__, type(native).__module__)
        self.assertEqual(public.digest(), native.digest())


if __name__ == "__main__":
    unittest.main()
