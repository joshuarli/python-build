"""Public routing and escaped HASH ownership across immutable module metadata."""
import gc
import hashlib
import importlib
import sys
import unittest

import _hashlib
import _hashlib_rs as native


NAMES = ("md5", "sha1", "sha224", "sha256", "sha384", "sha512")


class SlotExportTests(unittest.TestCase):
    def test_native_methods_type_metadata_and_errors(self):
        self.assertEqual(native.__doc__, "RustCrypto digest implementations used by hashlib.")
        self.assertEqual(native.new.__name__, "new")
        self.assertEqual(native.new.__module__, "_hashlib_rs")
        self.assertIs(native.new.__self__, native)
        self.assertEqual(native.new.__doc__, "Create a Rust-backed fixed-output digest object.")
        for name in NAMES:
            with self.subTest(name=name):
                context = native.new(name, b"prefix")
                oracle = _hashlib.new(name, b"prefix", usedforsecurity=False)
                self.assertIs(type(context), native.HASH)
                self.assertEqual(context.name, name)
                self.assertEqual(context.block_size, oracle.block_size)
                self.assertEqual(context.digest_size, oracle.digest_size)
                self.assertEqual(context.digest(), oracle.digest())
                self.assertEqual(context.hexdigest(), oracle.hexdigest())
                self.assertIsNone(context.update(b"suffix"))
                oracle.update(b"suffix")
                self.assertEqual(context.copy().digest(), oracle.digest())
                with self.assertRaises(TypeError):
                    hash(context)
                with self.assertRaises(AttributeError):
                    context.name = "other"
        with self.assertRaises(TypeError):
            native.HASH()
        with self.assertRaises(TypeError):
            native.new()
        with self.assertRaises(TypeError):
            native.new(name="sha256")
        with self.assertRaisesRegex(ValueError, "unsupported hash algorithm"):
            native.new("unsupported", b"")
        with self.assertRaises(TypeError):
            native.new("sha256", "text")

    def test_retained_factory_and_contexts_survive_reload_and_collection(self):
        factory = native.new
        hash_type = native.HASH
        baseline = sys.getrefcount(hash_type)
        contexts = [factory(name, b"before") for name in NAMES]
        copies = [context.copy() for context in contexts]
        self.assertIs(importlib.reload(native), native)
        self.assertIs(native.new, factory)
        self.assertIs(native.HASH, hash_type)
        del contexts
        gc.collect()
        for name, copied in zip(NAMES, copies):
            copied.update(b"after")
            self.assertIs(type(copied), hash_type)
            self.assertEqual(copied.digest(), _hashlib.new(name, b"beforeafter", usedforsecurity=False).digest())
        del copied, copies
        gc.collect()
        self.assertEqual(sys.getrefcount(hash_type), baseline)
        self.assertIs(type(factory("sha256", b"")), hash_type)

    def test_public_dispatch_monkeypatch_and_unavailable_helper_fallback(self):
        original = native.new
        cached = hashlib._rust_hash_module
        calls = []

        def record(name, data):
            calls.append(name)
            return original(name, data)

        try:
            native.new = record
            hashlib._rust_hash_module = native
            for name in NAMES:
                direct = getattr(hashlib, name)(b"data", usedforsecurity=False)
                generic = hashlib.new(name, b"data", usedforsecurity=False)
                self.assertIs(type(direct), native.HASH)
                self.assertIs(type(generic), native.HASH)
                self.assertEqual(direct.digest(), generic.digest())
            self.assertEqual(calls, [name for name in NAMES for _ in range(2)])
            hashlib._rust_hash_module = False
            fallback = hashlib.sha256(b"data", usedforsecurity=False)
            self.assertIs(type(fallback), _hashlib.HASH)
            self.assertEqual(fallback.digest(), original("sha256", b"data").digest())
        finally:
            native.new = original
            hashlib._rust_hash_module = cached


if __name__ == "__main__":
    unittest.main()
