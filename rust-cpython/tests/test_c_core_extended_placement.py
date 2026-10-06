"""The eighteen selected original C modules use builtin placement."""
import importlib
import sys
import unittest


MODULES = ('_struct', '_heapq', '_math_integer', 'math', 'fcntl', 'select',
           '_json', '_queue', '_random', '_statistics', 'array', '_socket',
           '_posixsubprocess', 'termios', '_zoneinfo', '_interpreters',
           'unicodedata', '_blake2')


class ExtendedCCorePlacementTests(unittest.TestCase):
    def test_eighteen_original_c_modules_and_original_rust_neighbors(self):
        for name in MODULES:
            with self.subTest(module=name):
                module = importlib.import_module(name)
                self.assertIn(name, sys.builtin_module_names)
                self.assertEqual(module.__spec__.origin, 'built-in')
                self.assertFalse(hasattr(module, '__file__'))
        for name in ('_struct_rs', '_json_rs', '_statistics_rs', '_socket_rs', '_unicodedata_rs', '_subprocess_rs'):
            with self.subTest(helper=name):
                module = importlib.import_module(name)
                self.assertNotIn(name, sys.builtin_module_names)
                self.assertTrue(module.__file__.endswith('.so'))


if __name__ == '__main__':
    unittest.main()
