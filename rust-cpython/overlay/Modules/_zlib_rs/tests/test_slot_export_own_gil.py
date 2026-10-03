"""Isolated-interpreter stream destruction and live export ownership."""
import unittest
import _interpreters
import _zlib_rs as native
import _zlib_slot_export_abi as oracle


class OwnGilSlotExportTests(unittest.TestCase):
    def test_inner_capsules_destroy_and_outer_method_survives(self):
        method = native.compress_once
        outer = native.compressor(0, 15)
        interpreter = _interpreters.create("isolated")
        try:
            self.assertEqual(_interpreters.get_config(interpreter).gil, "own")
            script = """
import importlib
import importlib.util
import _zlib_rs as native
import zlib
spec = importlib.util.spec_from_file_location('_zlib_slot_export_abi', ORACLE_PATH)
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)
assert oracle.check(native.__file__) is None
held = native.compress_once
assert held.__self__ is native
assert importlib.reload(native) is native
assert native.compress_once is held
compressor = zlib.compressobj(0)
duplicate = compressor.copy()
packed = compressor.compress(b'isolated capsules') + compressor.flush()
assert duplicate.compress(b'isolated capsules') + duplicate.flush() == packed
assert zlib.decompress(packed) == b'isolated capsules'
decoder = zlib.decompressobj()
assert decoder.decompress(packed + b'tail') == b'isolated capsules'
assert decoder.eof and decoder.unused_data == b'tail'
unfinalized = native.compressor(0, 15)
unfinalized_decoder = native.decompressor(15)
""".replace("ORACLE_PATH", repr(oracle.__file__))
            self.assertIsNone(_interpreters.run_string(interpreter, script))
        except BaseException as primary:
            try:
                _interpreters.destroy(interpreter)
            except BaseException as cleanup:
                primary.add_note(f"interpreter destruction also failed: {cleanup!r}")
            raise
        else:
            _interpreters.destroy(interpreter)
        self.assertIs(native.compress_once, method)
        self.assertIs(method.__self__, native)
        packed = native.compress(outer, b"outer survives") + native.flush(outer, 4)
        self.assertEqual(native.decompress_once(packed, 15), b"outer survives")
        self.assertEqual(native.decompress_once(method(b"held method", 0, 15), 15), b"held method")
        self.assertIsNone(oracle.check(native.__file__))


if __name__ == "__main__":
    unittest.main()
