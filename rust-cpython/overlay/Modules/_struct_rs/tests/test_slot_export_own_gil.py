"""The private helper retains shared-GIL-only interpreter admission."""
import unittest

import _interpreters
import _struct_rs as native


class OwnGilSlotExportTests(unittest.TestCase):
    def test_shared_admission_isolated_rejection_and_outer_survival(self):
        method = native.pack
        shared = _interpreters.create("legacy")
        try:
            self.assertEqual(_interpreters.get_config(shared).gil, "shared")
            self.assertIsNone(_interpreters.run_string(shared, """
import _struct_rs as native
assert native.pack.__self__ is native
assert native.pack('<I', (17,)) == b'\\x11\\x00\\x00\\x00'
assert native.unpack('<I', b'\\x11\\x00\\x00\\x00') == (17,)
native.pack = lambda *args: b'interpreter-local sentinel'
assert native.pack('<I', (17,)) == b'interpreter-local sentinel'
"""))
        except BaseException as primary:
            try:
                _interpreters.destroy(shared)
            except BaseException as cleanup:
                primary.add_note(f"shared interpreter destruction also failed: {cleanup!r}")
            raise
        else:
            _interpreters.destroy(shared)
        self.assertIs(native.pack, method)
        interpreter = _interpreters.create("isolated")
        try:
            self.assertEqual(_interpreters.get_config(interpreter).gil, "own")
            result = _interpreters.run_string(interpreter, """
try:
    import _struct_rs
except ImportError:
    pass
else:
    raise AssertionError('struct helper unexpectedly admitted an own-GIL interpreter')
import struct
import _struct
assert struct.Struct is _struct.Struct
assert struct.error is _struct.error
assert struct.pack('<I', 17) == b'\\x11\\x00\\x00\\x00'
assert struct.unpack('<I', b'\\x11\\x00\\x00\\x00') == (17,)
assert struct.unpack_from('<I', b'x\\x11\\x00\\x00\\x00', 1) == (17,)
""")
            self.assertIsNone(result)
        except BaseException as primary:
            try:
                _interpreters.destroy(interpreter)
            except BaseException as cleanup:
                primary.add_note(f"interpreter destruction also failed: {cleanup!r}")
            raise
        else:
            _interpreters.destroy(interpreter)
        self.assertIs(native.pack, method)
        self.assertIs(method.__self__, native)
        self.assertEqual(method("<I", (17,)), b"\x11\x00\x00\x00")


if __name__ == "__main__":
    unittest.main()
