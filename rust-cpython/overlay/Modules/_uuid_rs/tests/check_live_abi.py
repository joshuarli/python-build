"""Exercise registered native pointers through a pinned-header C observer."""
import importlib.util
import sys
import _uuid_rs as native
spec = importlib.util.spec_from_file_location('_uuid_rs_abi_test', sys.argv.pop(1))
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)
observer.module_contract(native)
raw = bytes.fromhex('12345678123456781234567812345678')
for name, args in (
    ('parse_hex', (raw.hex().encode(),)), ('normalize', (raw,)),
    ('set_version', (raw, b'\x04')), ('uuid3', (raw + b'name',)),
    ('uuid5', (raw + b'name',)), ('format', (raw,)), ('format_hex', (raw,)),
):
    assert observer.drive(native, name, args) == getattr(native, name)(*args)
random = observer.drive(native, 'uuid4', ())
assert len(random) == 16 and random[6] >> 4 == 4 and random[8] >> 6 == 2
print('OK _uuid_rs pinned-header live native ABI')
