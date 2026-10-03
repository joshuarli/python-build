"""Exercise the live C-header method/definition contract of the private API."""
import json
import _json_rs as native
import _json_workspace_allocator_fixture as fixture

values = [None, True, False, 0, -2**63, 2**63 - 1, 1.25,
          '', 'ASCII\x00text', '\u00e9', '\u1234', '\U0001f600',
          ['ASCII', '\u00e9', '\u1234', '\U0001f600', None, 1],
          {'\u1234': [True, False, 1.25], 'same': 'value'}]
for value in values:
    encoded, decoded = fixture.ffi_fast_roundtrip(native, value)
    assert decoded == value
    assert encoded == json.JSONEncoder().encode(value)
    assert json.JSONDecoder().decode(encoded) == value
for callee in (native.dumps, native.loads):
    for arguments in ((), (1, 2)):
        try:
            callee(*arguments)
        except TypeError:
            pass
        else:
            raise AssertionError('native FASTCALL arity accepted')
assert native.loads(1) is NotImplemented
assert native.dumps(set()) is None
print('OK private native header layouts, FASTCALL ownership and exported Unicode APIs')
