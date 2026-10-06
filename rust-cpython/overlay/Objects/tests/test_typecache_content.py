"""Observable type lookup behavior with distinct equal Unicode names."""
import gc
import sys
import unittest
import _testlimitedcapi

getattr_string = _testlimitedcapi.object_getattrstring


class TypeCacheContentTests(unittest.TestCase):
    def test_fresh_names_keep_caller_identity_and_descriptor_dispatch(self):
        seen = []
        calls = []
        class Descriptor:
            def __get__(self, obj, owner):
                calls.append(obj)
                return 42
        class Target:
            content_cache_attribute = Descriptor()
            def __getattribute__(self, name):
                seen.append(name)
                return object.__getattribute__(self, name)
        obj = Target()
        for _ in range(64):
            self.assertEqual(getattr_string(obj, b'content_cache_attribute'), 42)
        self.assertEqual(len({id(name) for name in seen}), 64)
        self.assertTrue(all(name == 'content_cache_attribute' for name in seen))
        self.assertEqual(calls, [obj] * 64)

    def test_class_mutation_and_negative_cache_follow_live_mro(self):
        class Base:
            value = 1
        class Child(Base):
            pass
        obj = Child()
        for _ in range(8): self.assertEqual(getattr_string(obj, b'value'), 1)
        Base.value = 2
        self.assertEqual(getattr_string(obj, b'value'), 2)
        for _ in range(8):
            with self.assertRaises(AttributeError): getattr_string(obj, b'absent')
        Base.absent = 3
        self.assertEqual(getattr_string(obj, b'absent'), 3)
        del Base.value
        with self.assertRaises(AttributeError): getattr_string(obj, b'value')

    def test_descriptor_reentry_and_error_identity(self):
        error = RuntimeError('descriptor sentinel')
        class Descriptor:
            def __get__(self, obj, owner):
                self.result = getattr_string(obj, b'nested')
                raise error
        descriptor = Descriptor()
        class Target:
            value = descriptor
            nested = 17
        obj = Target()
        for _ in range(4):
            with self.assertRaises(RuntimeError) as caught: getattr_string(obj, b'value')
            self.assertIs(caught.exception, error)
            self.assertEqual(descriptor.result, 17)
            error.__traceback__ = None

    def test_utf8_nul_and_exact_string_subclass_paths(self):
        class Name(str):
            def __hash__(self):
                raise RuntimeError('subclass hashing sentinel')
        class Target:
            pass
        obj = Target()
        setattr(Target, 'café', 5)
        self.assertEqual(getattr_string(obj, 'café'.encode()), 5)
        self.assertEqual(getattr_string(obj, 'café'.encode() + b'\0ignored'), 5)
        with self.assertRaises(UnicodeDecodeError): getattr_string(obj, b'\xff')
        with self.assertRaisesRegex(RuntimeError, 'subclass hashing sentinel'):
            getattr(obj, Name('café'))

    def test_high_cardinality_and_cache_clear_preserve_values(self):
        class Target:
            pass
        obj = Target()
        for index in range(5000): setattr(Target, 'lookup_%05d' % index, index)
        for index in range(5000):
            self.assertEqual(getattr_string(obj, ('lookup_%05d' % index).encode()), index)
        sys._clear_internal_caches()
        gc.collect()
        self.assertEqual(getattr_string(obj, b'lookup_04999'), 4999)
        Target.lookup_04999 = 'changed'
        self.assertEqual(getattr_string(obj, b'lookup_04999'), 'changed')


if __name__ == '__main__': unittest.main()
