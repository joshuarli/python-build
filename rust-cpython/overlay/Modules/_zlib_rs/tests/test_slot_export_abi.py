"""Live image export, method pointers, state size, and module token contract."""
import unittest
import _zlib_rs as native
import _zlib_slot_export_abi as oracle


class SlotExportAbiTests(unittest.TestCase):
    def test_live_image_export_and_method_ownership(self):
        self.assertIsNone(oracle.check(native.__file__))


if __name__ == "__main__":
    unittest.main()
