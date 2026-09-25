# Quote cache contract, 2026-09-25

This cache-priming revision was superseded after complete-workload diagnostics
showed that it leaves only one native call per safe value and raises CPU
against the pure parser. The current guard and its private-state tradeoff are
recorded in [the cache cost result](url-quote-cache-cost-20260925.md).

The guarded `quote_from_bytes` route now primes an empty `_Quoter` through its original bound `__getitem__` once per distinct byte, in first appearance order, before the Rust output scan. `dict.fromkeys(bs)` preserves that order for exact `bytes`. The baseline's later hits on repeated bytes do not write to the dict, so the final keys, insertion order, and cached string values match. This preserves the private cached `_Quoter` object returned by `_byte_quoter_factory(safe)` while still leaving the complete output scan in Rust. The guard also checks that `_Quoter.__setitem__` retains its captured implementation.

The native route requires `1 < len(bs) < 200_000`. For a one byte input, `''.join(map(quoter, bs))` returns the cached string object itself on CPython. The native extension makes a distinct Unicode object, so one byte calls stay on the original path. For longer input, both paths return a new joined/output string, while each cached fragment is the exact string returned by the same `_Quoter.__missing__` call. Inputs whose quoter dict is already populated also stay on the original path; modified cached values therefore remain effective. Nonexact inputs, changed relevant bindings, large inputs, and calls with `sys.gettrace()` or `sys.getprofile()` active retain the fallback.

## Bounded diagnostic

The local host is CPython 3.13.7; this diagnostic exercises the same `_Quoter` cache algorithm, not the pinned 3.16 interpreter or compiled Rust extension. For each case, it compared `''.join(map(baseline.__getitem__, value))` with a second quoter primed by `for byte in dict.fromkeys(value): primed.__getitem__(byte)`. It compared `dict(baseline) == dict(primed)` and `list(baseline) == list(primed)` after the calls.

| Case | Cache values equal | Key order equal | Entries | First keys |
| --- | --- | --- | ---: | --- |
| `b'not safe /% not safe'`, safe `/` | yes | yes | 10 | `110, 111, 116, 32, 115, 97, 102, 101` |
| `bytes(range(256)) + bytes(range(255, -1, -1))`, safe `/` | yes | yes | 256 | `0, 1, 2, 3, 4, 5, 6, 7` |
| `b'/x y/y%z'`, safe `/%` | yes | yes | 6 | `47, 120, 32, 121, 37, 122` |
| `b' '`, safe empty | yes | yes | 1 | `32` |

The same host reports `result is cached_fragment` as true for `b' '`, false for `b'  '`, and false for `b' /'`, each with safe `/`. This supports the one byte identity exclusion separately from cache-value equality.

`git apply --stat rust-cpython/patches/0001-rust-url-quote.patch` accepted the edited patch structure. The hunk counts were independently checked against their bodies. No full build, test suite, formatter, linter, hook, or timing run was made under the current shared host load.

## Limits

This restores the final quoter cache state under the guarded stable-binding conditions. A trace or profile hook active when the guard runs takes the original path because it can otherwise observe one bound quoter `__getitem__` call per distinct byte instead of one per input byte. The guard itself adds observable calls and lines, so exact event-stream parity under instrumentation is not claimed. A hook installed after the guard, concurrent mutation or observation during a call, and code that dynamically changes relevant objects between guard and use can still distinguish the paths. Priming also adds a second input scan and up to 256 Python quoter calls; complete workload value needs a quiet-host measurement after integration. Keep this Rust route opt-in until installed 3.16 semantic qualification and paired performance and memory evidence are complete.
