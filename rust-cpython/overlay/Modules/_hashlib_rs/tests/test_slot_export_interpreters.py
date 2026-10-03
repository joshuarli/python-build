"""Shared-GIL admission and own-GIL rejection retain the native provider contract."""
import unittest

import _hashlib_rs as native
import _interpreters


class SlotExportInterpreterTests(unittest.TestCase):
    def run_in_interpreter(self, configuration, script):
        interpreter = _interpreters.create(configuration)
        try:
            result = _interpreters.run_string(interpreter, script)
            self.assertIsNone(result)
        except BaseException as primary:
            try:
                _interpreters.destroy(interpreter)
            except BaseException as cleanup:
                primary.add_note(f"interpreter destruction also failed: {cleanup!r}")
            raise
        else:
            _interpreters.destroy(interpreter)

    def test_shared_gil_native_heap_type_is_interpreter_local(self):
        outer = native.new("sha256", b"outer")
        self.run_in_interpreter("legacy", f"""
import _hashlib_rs as native
import importlib
assert id(native.HASH) != {id(native.HASH)}
factory = native.new
context = factory('sha256', b'inner')
copied = context.copy()
assert copied.digest() == context.digest()
assert importlib.reload(native) is native
assert native.new is factory
assert type(copied) is native.HASH
copied.update(b' next')
assert copied.digest() != context.digest()
""")
        self.assertIs(type(outer), native.HASH)
        self.assertEqual(outer.copy().digest(), native.new("sha256", b"outer").digest())

    def test_own_gil_import_remains_rejected(self):
        self.run_in_interpreter("isolated", """
try:
    import _hashlib_rs
except ImportError as error:
    assert '_hashlib_rs' in str(error)
else:
    raise AssertionError('shared-GIL-only helper imported under its own GIL')
""")
        self.assertEqual(len(native.new("sha256", b"outer").digest()), 32)


if __name__ == "__main__":
    unittest.main()
