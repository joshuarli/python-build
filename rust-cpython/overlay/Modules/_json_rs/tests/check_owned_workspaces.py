"""Observe JSON workspace growth, key collisions, ownership and decline behavior."""
import gc
import json
import weakref
import _json_rs as native


def main():
    text = '[' + ','.join('{"shared-name-€": %d}' % i for i in range(200)) + ']'
    value = native.loads(text)
    assert value == json.JSONDecoder().decode(text)
    keys = [next(iter(item)) for item in value]
    assert all(key is keys[0] for key in keys)
    distinct = '{' + ','.join('"key-%d": %d' % (i, i) for i in range(200)) + '}'
    assert native.loads(distinct) == json.JSONDecoder().decode(distinct)
    escaped = json.dumps(['line\n€😀' * 100, 10**500, -(10**500), 1.25e100])
    assert native.loads(escaped) == json.JSONDecoder().decode(escaped)
    nested = '[' * 40 + '0' + ']' * 40
    assert native.loads(nested) == json.JSONDecoder().decode(nested)
    for invalid in ('[1,', '{"a": [1, 2],', '["large' + 'x' * 1000,
                    '{"a":1} trailing', 'NaN', '"\\ud800"'):
        assert native.loads(invalid) is NotImplemented
    class Text(str):
        pass
    borrowed = Text(text)
    owner = weakref.ref(borrowed)
    held = native.loads(borrowed)
    del borrowed
    gc.collect()
    assert owner() is None and held == value
    assert native.dumps({'escaped': '\n€😀', 'nested': [True, None, 7]}) == json.dumps(
        {'escaped': '\n€😀', 'nested': [True, None, 7]})
    assert native.dumps({1, 2}) is None
    assert json.loads('{"dup":1,"dup":2}') == {'dup': 2}
    print('OK JSON owned workspace growth, shared byte keys, parse cleanup and encoder parity')


if __name__ == '__main__':
    main()
