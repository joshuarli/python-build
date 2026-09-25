# URL unquote mutable-state decision, 2026-09-25

**Defer optional patch 0004.** Its native return in public `unquote` changes
observable CPython 3.16 behavior. Keep the existing patch opt-in and do not
promote it until a replacement preserves the state and hook boundaries below.

## Pinned source and diagnostic recipe

The source is Rust-for-CPython commit
`b812b4a7b9efaca46b98544a8633b7d7e454166b`, pinned by
`rust-cpython/sources.lock.json`. In its `Lib/urllib/parse.py`, public
`unquote` calls `_generate_unquoted_parts`; each ASCII run calls
`_unquote_impl`. The latter initializes `_hextobyte` only after an input
containing `%` reaches it, then indexes the current mapping with the next
zero to two bytes after **every** percent sign. A missing key preserves that
percent segment. Thus added malformed keys, removed valid keys, and replaced
values all affect output. Patch 0004 returns before these operations.

The following read-only diagnostic ran with the pinned source placed first on
`PYTHONPATH` and the existing CPython 3.16 interpreter. It did not load the
optional native patch:

```sh
PYTHONPATH=/Users/josh/d/python-build/rust-cpython/work/source-no-rust/cpython-b812b4a7b9efaca46b98544a8633b7d7e454166b/Lib \
  /Users/josh/d/python-build/rust-cpython/stage/bin/python3.16 -S - <<'PY'
import urllib.parse as p
print('source', p.__file__)
print('lazy_before', p._hextobyte is None)
print('first', p.unquote('%41'), 'lazy_after', p._hextobyte is not None)
p._hextobyte[b'41'] = b'Z'
print('mutated_valid', p.unquote('%41'))
p._hextobyte[b'xx'] = b'Q'
print('mutated_malformed', p.unquote('%xx'))
del p._hextobyte[b'41']
print('deleted_valid', p.unquote('%41'))
p._generate_unquoted_parts = lambda *args: iter(('HOOK',))
print('rebound_generator', p.unquote('%41'))
PY
```

Output: `lazy_before True`; `first A lazy_after True`;
`mutated_valid Z`; `mutated_malformed Q`; `deleted_valid %41`;
`rebound_generator HOOK`. The source path printed by the diagnostic was the
pinned `Lib/urllib/parse.py` above. The unpatched source file SHA-256 was
`178fce6bb504b9e544ac22015778554234c63865d94374913f988bb731e0d825`;
patch 0004 was `27c0e4c21be013830d253215db25a1f3f04566755a2d5e19e879977ceae033a7`.

## Contract-preserving route to investigate

Put any native byte scan inside `_unquote_impl`, after its normal lazy table
initialization. Keep public `unquote`, `_generate_unquoted_parts`, and the
regex traversal intact, so their Python calls and replacements remain
observable. The native helper must use the current mapping for every percent
segment, including malformed and incomplete escapes, and preserve
`bytearray.extend` behavior for unusual mapping values or fall back before
mutating an output buffer. A helper that hard-codes hexadecimal decoding
cannot meet that contract. Rebinding `_unquote_impl` must still intercept the
call from `_generate_unquoted_parts`; tracing and profiling also see the
original Python call boundaries with this placement.

This route requires a new C/Python boundary and a fresh same-workload speed
assessment. No source build, test suite, benchmark, formatter, linter, or hook
was run for this decision. The present audit only establishes the mismatch
and the necessary placement of a compatible route.
