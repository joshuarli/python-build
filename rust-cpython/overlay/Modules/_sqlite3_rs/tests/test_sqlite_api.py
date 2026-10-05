import ctypes
import importlib.util
import unittest

import _sqlite3
import _sqlite3_rs


class ApiHeader(ctypes.Structure):
    _fields_ = [('version', ctypes.c_uint32), ('size', ctypes.c_size_t)]


Step = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p)
ColumnInt = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_int)
ColumnInt64 = ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_void_p, ctypes.c_int)
ColumnDouble = ctypes.CFUNCTYPE(ctypes.c_double, ctypes.c_void_p, ctypes.c_int)
ColumnPointer = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int)
ErrorCode = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p)


class ApiTable(ctypes.Structure):
    _fields_ = ApiHeader._fields_ + [
        ('step', Step), ('column_type', ColumnInt),
        ('column_int64', ColumnInt64), ('column_double', ColumnDouble),
        ('column_text', ColumnPointer), ('column_blob', ColumnPointer),
        ('column_bytes', ColumnInt), ('errcode', ErrorCode)]


new_capsule = ctypes.pythonapi.PyCapsule_New
new_capsule.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p]
new_capsule.restype = ctypes.py_object
get_pointer = ctypes.pythonapi.PyCapsule_GetPointer
get_pointer.argtypes = [ctypes.py_object, ctypes.c_char_p]
get_pointer.restype = ctypes.c_void_p
CAPSULE_NAME = b'_sqlite3._RUST_API'


def fresh_helper():
    spec = importlib.util.spec_from_file_location('_sqlite3_rs', _sqlite3_rs.__file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SQLiteApiTests(unittest.TestCase):
    def test_c_owner_exports_complete_versioned_api(self):
        pointer = get_pointer(_sqlite3._RUST_API, CAPSULE_NAME)
        table = ctypes.cast(pointer, ctypes.POINTER(ApiTable)).contents
        self.assertEqual(table.version, 1)
        self.assertEqual(table.size, ctypes.sizeof(ApiTable))
        for name, _ in ApiTable._fields_[2:]:
            self.assertTrue(bool(getattr(table, name)), name)
        connection = _sqlite3.connect(':memory:')
        try:
            self.assertEqual(connection.execute('select 42').fetchone(), (42,))
        finally:
            connection.close()

    def test_fresh_helper_rejects_invalid_api_then_recovers(self):
        original = _sqlite3._RUST_API
        wrong_version = ApiTable()
        wrong_version.version = 2
        wrong_version.size = ctypes.sizeof(ApiTable)
        truncated = ApiHeader(1, ctypes.sizeof(ApiHeader))
        null_callbacks = ApiTable()
        null_callbacks.version = 1
        null_callbacks.size = ctypes.sizeof(ApiTable)
        cases = [None, object(), wrong_version, truncated, null_callbacks]
        try:
            for value in cases:
                with self.subTest(case=type(value).__name__):
                    if value is None:
                        del _sqlite3._RUST_API
                    elif isinstance(value, ctypes.Structure):
                        _sqlite3._RUST_API = new_capsule(ctypes.addressof(value), CAPSULE_NAME, None)
                    else:
                        _sqlite3._RUST_API = value
                    with self.assertRaises((ImportError, AttributeError)):
                        fresh_helper()
                    _sqlite3._RUST_API = original
                    helper = fresh_helper()
                    self.assertIs(helper.step.__self__, helper)
                    self.assertIs(helper.column.__self__, helper)
        finally:
            _sqlite3._RUST_API = original


if __name__ == '__main__':
    unittest.main()
