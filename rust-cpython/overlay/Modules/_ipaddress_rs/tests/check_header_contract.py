"""Validate the live method definitions using the compiled header observer."""
import unittest
import _ipaddress_rs
import _ipaddress_header_contract


class LiveAddressHeaderContract(unittest.TestCase):
    def test_live_module_and_callbacks(self):
        self.assertIsNone(_ipaddress_header_contract.check(_ipaddress_rs))
        self.assertEqual(_ipaddress_rs.parse_ipv4('127.0.0.1'), b'\x7f\0\0\1')
        value = bytearray(range(16))
        self.assertEqual(_ipaddress_rs.network_bounds(value, 128), bytes(value) * 2)
        value.extend(b'x')


if __name__ == '__main__':
    unittest.main()
