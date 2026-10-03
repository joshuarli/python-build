"""Isolated-interpreter ownership through separately admitted startup."""
import unittest

import _interpreters
import _pickle_rs as native


class PickleOwnGilSlotExportTests(unittest.TestCase):
    def test_isolated_module_mutation_destroy_and_retained_outer_methods(self):
        methods = (native.dumps, native.loads)
        interpreter = _interpreters.create("isolated")
        try:
            self.assertEqual(_interpreters.get_config(interpreter).gil, "own")
            self.assertIsNone(_interpreters.run_string(interpreter, """
import importlib
import io
import pickle
import _pickle
import _pickle_rs as native
value = {'items': [None, True, -17, b'payload']}
encoded = native.dumps(value, 5)
assert native.loads(encoded) == (True, value, len(encoded))
assert native.dumps.__self__ is native and native.loads.__self__ is native
held = native.dumps
assert importlib.reload(native) is native and native.dumps is held
assert pickle.Pickler is _pickle.Pickler and pickle.Unpickler is _pickle.Unpickler
assert pickle.loads(pickle.dumps(value, protocol=5)) == value
stream = io.BytesIO()
pickle.dump(value, stream, protocol=5)
stream.seek(0)
assert pickle.load(stream) == value
native.dumps = lambda *args: None
assert pickle.loads(pickle.dumps((1, 2), protocol=5)) == (1, 2)
"""))
        except BaseException as primary:
            try:
                _interpreters.destroy(interpreter)
            except BaseException as cleanup:
                primary.add_note(f"interpreter destruction also failed: {cleanup!r}")
            raise
        else:
            _interpreters.destroy(interpreter)
        self.assertIs(native.dumps, methods[0])
        self.assertIs(native.loads, methods[1])
        self.assertIs(methods[0].__self__, native)
        encoded = methods[0]([1, 2], 5)
        self.assertEqual(methods[1](encoded), (True, [1, 2], len(encoded)))


if __name__ == "__main__":
    unittest.main()
