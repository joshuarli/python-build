"""Validate live native definitions using the compiled CPython-header observer."""
import importlib.util
import sys
import binascii
import _binascii_rs

spec = importlib.util.spec_from_file_location('_binascii_allocation_test', sys.argv.pop(1))
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)
observer.module_contract(_binascii_rs)
for name in ('b2a_hex', 'hexlify', 'a2b_hex', 'unhexlify', 'crc32', 'crc_hqx'):
    assert getattr(binascii, name) is getattr(_binascii_rs, name)
assert _binascii_rs.crc32(b'123456789') == 0xcbf43926
assert _binascii_rs.crc_hqx(b'123456789', 0) == 0x31c3
assert _binascii_rs.hexlify(b'abc', sep=b':', bytes_per_sep=1) == b'61:62:63'
assert _binascii_rs.unhexlify(b'61:62:63', ignorechars=b':') == b'abc'
print('OK binascii pinned-header and live native method ABI')
