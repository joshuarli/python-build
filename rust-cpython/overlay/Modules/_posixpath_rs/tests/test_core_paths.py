"""POSIX lexical path behavior across stack and Python-owned scratch buffers."""
import importlib
import posixpath
import unittest

import _posixpath_rs


class CorePathTests(unittest.TestCase):
    def test_direct_methods_preserve_text_and_byte_units(self):
        for path, expected in (("", "."), ("//a///b/../c", "//a/c"),
                               ("../a/../../b", "../../b"), ("/a/../../b", "/b"),
                               ("α/😀/../x\0y", "α/x\0y"),
                               ("\ud800/a/../b", "\ud800/b")):
            self.assertEqual(_posixpath_rs._path_normpath(path), expected)
            if not any(0xD800 <= ord(unit) <= 0xDFFF for unit in path):
                raw = path.encode()
                self.assertEqual(_posixpath_rs._path_normpath(raw), expected.encode())
        for path, split, root, extension in (
                ("//a///b.ext", ("//a", "b.ext"), ("", "//", "a///b.ext"), ("//a///b", ".ext")),
                ("///", ("///", ""), ("", "/", "//"), ("///", "")),
                (".hidden", ("", ".hidden"), ("", "", ".hidden"), (".hidden", ""))):
            for byte_mode in (False, True):
                convert = lambda value: value.encode() if byte_mode else value
                self.assertEqual(_posixpath_rs.split(convert(path)), tuple(map(convert, split)))
                self.assertEqual(_posixpath_rs._path_splitroot_ex(convert(path)), tuple(map(convert, root)))
                self.assertEqual(_posixpath_rs.splitext(convert(path)), tuple(map(convert, extension)))
                self.assertEqual(_posixpath_rs.join_pair(convert("a/"), convert("b")), convert("a/b"))
                self.assertEqual(_posixpath_rs.join_pair(convert("a"), convert("/b")), convert("/b"))

    def test_stack_boundary_and_long_python_scratch_results_remain_owned(self):
        retained = []
        for length in (0, 511, 512, 513, 4096):
            for byte_mode in (False, True):
                slash = b"/" if byte_mode else "/"
                dot = b".ext" if byte_mode else ".ext"
                leaf = b"leaf" if byte_mode else "leaf"
                unit = b"x" if byte_mode else "α"
                empty = b"" if byte_mode else ""
                component = unit * max(0, length - 9)
                path = component + slash + leaf + dot if length else empty
                self.assertEqual(len(path), length)
                expected = (component or slash, leaf + dot) if length else (empty, empty)
                result = _posixpath_rs.split(path)
                self.assertEqual(result, expected)
                self.assertEqual(_posixpath_rs._path_normpath(path), path or (b"." if byte_mode else "."))
                self.assertEqual(_posixpath_rs.splitext(path),
                                 (path[:-4], dot) if length else (empty, empty))
                retained.append((result, expected))
        for actual, expected in retained:
            self.assertEqual(actual, expected)

    def test_fspath_callbacks_errors_and_mixed_units(self):
        calls = []
        class Path:
            def __init__(self, value):
                self.value = value
            def __fspath__(self):
                calls.append(self.value)
                return self.value
        self.assertEqual(_posixpath_rs.join_pair(Path("a"), Path("b")), "a/b")
        self.assertEqual(calls, ["a", "b"])
        class Broken:
            def __fspath__(self):
                raise LookupError("path callback")
        for method in (_posixpath_rs._path_normpath, _posixpath_rs.split,
                       _posixpath_rs._path_splitroot_ex, _posixpath_rs.splitext):
            with self.assertRaisesRegex(LookupError, "path callback"):
                method(Broken())
            with self.assertRaises(TypeError):
                method(Path(1))
        with self.assertRaises(TypeError):
            _posixpath_rs.join_pair("a", b"b")
        with self.assertRaises(TypeError):
            _posixpath_rs.join_pair("a")
        with self.assertRaises(TypeError):
            _posixpath_rs.split("a", "b")

    def test_public_routes_still_call_original_native_methods(self):
        originals = {name: getattr(_posixpath_rs, name) for name in
                     ("_path_normpath", "join_pair", "split", "_path_splitroot_ex", "splitext")}
        calls = {name: 0 for name in originals}
        def forwarding(name):
            def call(*args):
                calls[name] += 1
                return originals[name](*args)
            return call
        try:
            for name in originals:
                setattr(_posixpath_rs, name, forwarding(name))
            self.assertEqual(posixpath.normpath("a/../b"), "b")
            self.assertEqual(posixpath.join("a", "b"), "a/b")
            self.assertEqual(posixpath.split("a/b"), ("a", "b"))
            self.assertEqual(posixpath.splitroot("//a/b"), ("", "//", "a/b"))
            self.assertEqual(posixpath.splitext("a/b.ext"), ("a/b", ".ext"))
            self.assertTrue(all(count > 0 for count in calls.values()), calls)
        finally:
            for name, method in originals.items():
                setattr(_posixpath_rs, name, method)

    def test_reload_preserves_held_native_callables(self):
        held = _posixpath_rs.split
        self.assertIs(importlib.reload(_posixpath_rs), _posixpath_rs)
        self.assertEqual(held("a/b"), ("a", "b"))
        self.assertEqual(_posixpath_rs.split("a/b"), ("a", "b"))


if __name__ == "__main__":
    unittest.main()
