"""Isolated-interpreter lifetime proof for separately admitted native startup."""
import unittest

import _datetime_rs as native
import _interpreters


class OwnGilSlotExportTests(unittest.TestCase):
    def test_isolated_interpreter_module_ownership_and_outer_survival(self):
        method = native.parse_date
        interpreter = _interpreters.create("isolated")
        try:
            self.assertEqual(_interpreters.get_config(interpreter).gil, "own")
            result = _interpreters.run_string(interpreter, """
import _datetime_rs as native
import _datetime
import datetime
import importlib
assert native.parse_date.__self__ is native
assert native.parse_date('2024-02-29') == (2024, 2, 29)
assert native.parse_time('12:34:56') == (12, 34, 56, 0)
assert native.format_date(2024, 2, 29) == '2024-02-29'
assert native.format_time(1, 2, 3, 0, 2) == '01:02:03'
assert native.format_datetime(2024, 2, 29, 1, 2, 3, 0, 84, 2) == '2024-02-29T01:02:03'
assert native.add_date(2024, 2, 28, 1) == (2024, 2, 29)
assert native.add_datetime(2024, 2, 29, 23, 59, 59, 999999, 0, 0, 1, 1) == (2024, 3, 1, 0, 0, 0, 0)
assert datetime.date is _datetime.date
assert type(_datetime.datetime_CAPI).__name__ == 'PyCapsule'
held = native.parse_date
assert importlib.reload(native) is native
assert native.parse_date is held
assert datetime.date(2024, 2, 28) + datetime.timedelta(days=1) == datetime.date(2024, 2, 29)
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
        self.assertIs(native.parse_date, method)
        self.assertIs(method.__self__, native)
        self.assertEqual(method("2024-02-29"), (2024, 2, 29))


if __name__ == "__main__":
    unittest.main()
