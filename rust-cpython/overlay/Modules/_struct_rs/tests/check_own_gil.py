"""Keep the existing helper capability and public fallback under an own GIL."""
import _interpreters

config = _interpreters.new_config('isolated', gil='own')
interpreter = _interpreters.create(config)
try:
    assert _interpreters.get_config(interpreter).gil == 'own'
    result = _interpreters.run_string(interpreter, """
import _struct
import struct
try:
    import _struct_rs
except ImportError:
    pass
else:
    raise AssertionError('helper unexpectedly admits the independent GIL')
assert struct.Struct is _struct.Struct
assert struct.error is _struct.error
values = (17, -129, b'abcd')
format = '<Ih4s'
expected = _struct.pack(format, *values)
assert struct.pack(format, *values) == expected
assert struct._get_rust_struct() is None
assert struct.unpack(format, expected) == values
assert struct.unpack_from(format, b'x' + expected, 1) == values
buffer = bytearray(len(expected))
assert struct.pack_into(format, buffer, 0, *values) is None
assert buffer == expected
buffer.extend(b'!')
try:
    struct.pack('<I', -1)
except struct.error:
    pass
else:
    raise AssertionError('invalid integer accepted')
""")
    assert result is None, result
finally:
    _interpreters.destroy(interpreter)
print('OK struct public fallback and baseline helper capability under an independent GIL')
