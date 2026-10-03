"""Isolated-interpreter counting lifetime contract for separately admitted startup."""
import unittest

import _collections_rs as native
import _interpreters


class OwnGilSlotExportTests(unittest.TestCase):
    def test_isolated_counting_and_outer_callable_survival(self):
        retained = native.subtract_iterable
        interpreter = _interpreters.create("isolated")
        try:
            self.assertEqual(_interpreters.get_config(interpreter).gil, "own")
            result = _interpreters.run_string(interpreter, """
import _collections_rs as native
import _collections
import collections
import importlib
assert native.subtract_iterable.__self__ is native
mapping = {"a": 2}
assert native.subtract_iterable(mapping, ("a", "b"), mapping.get) is None
assert mapping == {"a": 1, "b": -1}
held = native.subtract_iterable
assert importlib.reload(native) is native
assert native.subtract_iterable is held
counter = collections.Counter(a=2)
counter.subtract(("a", "b"))
assert counter == {"a": 1, "b": -1}
assert collections.deque is _collections.deque
assert collections.defaultdict is _collections.defaultdict
assert collections.OrderedDict is _collections.OrderedDict
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
        self.assertIs(native.subtract_iterable, retained)
        mapping = {}
        self.assertIsNone(retained(mapping, ("outer",), mapping.get))
        self.assertEqual(mapping, {"outer": -1})


if __name__ == "__main__":
    unittest.main()
