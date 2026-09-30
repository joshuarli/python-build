"""Hash context destruction releases the reference acquired to its heap type."""

import gc
import hashlib
import os
import sys
import unittest


EXPECTED_HASH_MODULE = os.environ.get("HASHLIB_EXPECTED_MODULE", "_hashlib_rs")
ALGORITHMS = ("md5", "sha1", "sha224", "sha256", "sha384", "sha512")


@unittest.skipUnless(sys.version_info[:2] == (3, 16), "requires the staged Python 3.16 interpreter")
class HashlibTypeLifetimeTests(unittest.TestCase):
    def hash_type(self, algorithm):
        context = getattr(hashlib, algorithm)(b"initial")
        hash_type = type(context)
        self.assertEqual(hash_type.__module__, EXPECTED_HASH_MODULE)
        self.assertTrue(hash_type.__flags__ & (1 << 9), "requires a heap type")
        del context
        gc.collect()
        return hash_type

    def test_context_destruction_releases_type_reference(self):
        for algorithm in ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                hash_type = self.hash_type(algorithm)
                strong_refs = sys.getrefcount(hash_type)
                context = getattr(hashlib, algorithm)(b"payload")
                self.assertIs(type(context), hash_type)
                self.assertEqual(sys.getrefcount(hash_type), strong_refs + 1)
                del context
                gc.collect()
                self.assertEqual(sys.getrefcount(hash_type), strong_refs)

    def test_copy_destruction_releases_type_reference(self):
        for algorithm in ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                context = getattr(hashlib, algorithm)(b"payload")
                hash_type = type(context)
                self.assertEqual(hash_type.__module__, EXPECTED_HASH_MODULE)
                gc.collect()
                strong_refs = sys.getrefcount(hash_type)
                copied = context.copy()
                self.assertIs(type(copied), hash_type)
                self.assertEqual(copied.digest(), context.digest())
                self.assertEqual(sys.getrefcount(hash_type), strong_refs + 1)
                del copied
                gc.collect()
                self.assertEqual(sys.getrefcount(hash_type), strong_refs)
                del context

    def test_repeated_contexts_do_not_retain_type_references(self):
        for algorithm in ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                hash_type = self.hash_type(algorithm)
                strong_refs = sys.getrefcount(hash_type)
                for _ in range(32):
                    context = getattr(hashlib, algorithm)(b"payload")
                    context.update(b"suffix")
                    context.hexdigest()
                    del context
                gc.collect()
                self.assertEqual(sys.getrefcount(hash_type), strong_refs)


if __name__ == "__main__":
    unittest.main()
