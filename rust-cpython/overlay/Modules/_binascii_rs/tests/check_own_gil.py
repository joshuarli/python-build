"""Exercise the native helper in an isolated interpreter with its own GIL."""
import _interpreters

config = _interpreters.new_config('isolated', gil='own')
interpreter = _interpreters.create(config)
try:
    assert _interpreters.get_config(interpreter).gil == 'own'
    result = _interpreters.run_string(interpreter, '''
import binascii
import _binascii_rs as native
payload = b'abcdefgh' * 1001
assert binascii.hexlify(payload) == native.hexlify(payload)
assert binascii.unhexlify(native.hexlify(payload)) == payload
assert native.b64decode(native.standard_b64encode(payload), True, True) == payload
assert native.b85decode(native.b85encode(payload, False)) == payload
assert native.b32decode(native.b32encode(payload, True), True) == payload
assert native.crc32(b'123456789') == 0xcbf43926
class LocalError(ValueError):
    pass
original = binascii.Error
binascii.Error = LocalError
try:
    try:
        native.unhexlify(b'z0')
    except LocalError:
        pass
    else:
        raise AssertionError('native helper ignored interpreter-local Error')
finally:
    binascii.Error = original
''')
    assert result is None, result
finally:
    _interpreters.destroy(interpreter)
print('OK binascii native helper with an independent GIL')
