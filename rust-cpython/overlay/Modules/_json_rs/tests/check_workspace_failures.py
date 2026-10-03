"""Require new workspace failures to propagate MemoryError with clean owners."""
import json
import _json_rs as native
import _json_workspace_allocator_fixture as fixture

# Controlled native documents use malloc/calloc for Python containers and
# realloc for the new workspaces. ASCII avoids a retained input UTF-8 cache.
texts = ['[' + ','.join(str(i) for i in range(200)) + ']',
         '{' + ','.join('"key-%d": %d' % (i, i) for i in range(200)) + '}',
         '["' + '\\n' * 1000 + '"]']
for callee in (native.loads, json.loads):
    for text in texts:
        calls, marker, failed, live, error = fixture.exercise(callee, text, 0)
        assert calls > 0 and not marker and not failed and live == 0 and error is None
        for index in range(1, calls + 1):
            count, marker, failed, live, error = fixture.exercise(callee, text, index)
            assert failed and not marker and live == 0 and isinstance(error, MemoryError), (
                index, count, marker, failed, live, error)
        assert native.loads(text) == json.JSONDecoder().decode(text)
assert native.loads('[1,') is NotImplemented
print('OK new workspace MemoryError propagation direct/public and zero remaining owners')
