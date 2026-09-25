# Quote cache priming cost, 2026-09-25

## Narrow patch revision

**Prefer the revised `0001` guard to the measured priming guard.** It removes
the priming loop and its unused `dict.fromkeys` capture, keeps the binding
checks, the one-byte exclusion, the trace/profile fallback, and the
empty-cache check. It adds a local comment explaining that populated quoter
caches use the original Python path. The revised patch SHA-256 is
`8117e87d51a91dd362d5c315f3eae552ac1144b83f43dae1980423c320b618ad`;
the revised source-overlay parser SHA-256 is
`f2949f2bfd61891f33a9e79168f1c188587b374985ebb3faa04a476202b280f2`.
The parser hunk applied with zero fuzz to a fresh copy of the pinned parser.
The C/Rust source and standalone native extension remain unchanged.

An untimed same-executable diagnostic compared the revised overlay with the
pure pinned parser using the same source-only bytecode policy. With a fresh
cache, public `quote_from_bytes(b'x y', safe=b'/')` returned `x%20y` in both;
the revised route made one native call. After deliberately setting the cached
fragment for byte 32 to `'<edited>'`, both returned `x<edited>y`, and the
revised route made zero native calls. Setting that fragment to `object()` made
both public calls raise the same `TypeError` with message
`sequence item 1: expected str instance, object found`; again zero revised
native calls. The one-byte call returned `%20` with zero native calls;
trace-active and profile-active calls both returned `x%20y` with zero native
calls. All exact observations are in `cache_edit_observations` in the raw JSON.

The remaining difference is private state: after the fresh native call, the
revised quoter cache had no keys, while the pure parser cache had keys
`[120, 32, 121]`. `_Quoter` and its factory are private implementation
details, yet code that deliberately inspects their cache can observe that
difference. Once such code edits or populates the cache, the revised guard
falls back and honors its values and errors through public calls. This is a
deliberate, limited semantic claim. The targeted diagnostic does not replace
full public differential qualification of the revised patch before an
upstream claim.

## Verdict

**The state-preserving route shows no complete-workload win on these two
diagnostic tasks.** Three serial pairs on each checked-in catalog task used the same
CPython 3.16 executable and one locally built quote extension. The only parser
difference was the two-line cache priming loop. Priming raised median paired
root kernel user-plus-system CPU by **15.2%** for `catalog_search_form` and
**7.6%** for `catalog_request_path`. All six CPU pairs showed a cost;
corresponding median paired wall increases were 13.5% and 6.1%. This puts the
earlier quote-only complete-task gains in question, but does not establish an
integrated speed regression. The unrelated OrbStack process consumed roughly
8–9 logical CPUs during the first comparison; these are diagnostic, not
publishable timings. A second bounded comparison against the pure pinned
parser found the primed route slower in all six CPU pairs: median paired
primed/baseline CPU ratios were **1.090** for search and **1.136** for path.
This makes a severe loss of the original quote-only value plausible, while
quiet-host integrated qualification remains open.

The first inventory stopped because the previously documented installed
patched stage was gone. A standalone diagnostic build was then authorized.
No main stage or other worktree was changed.

## Source, build, and cache identity

The accepted read-only stage `bin/python3.16` SHA-256 is
`6eeeb64b9eb161d4d5edb9200e79146dabd8acc0f73fcdca48417d0e3c9531bd`;
its original parser is
`178fce6bb504b9e544ac22015778554234c63865d94374913f988bb731e0d825`.
The priming version of `0001-rust-url-quote.patch` measured below had SHA-256
`0296c67e64c7f02f1f5ff374eca4d8d8e685323e59f8cd3f37edb467ce1c2f8f`.
Its C and Rust new-file hunks were extracted under ignored
`rust-cpython/work/url-quote-cache-cost-20260925/source`. Their Git blob IDs
match the patch headers: `19fa50a3a9e5595f3e8c26e4eafd3fac3cf8e207` for
`module.c` and `7b00ec5d47b8699089cd9cfac7b35a4076f092ba` for `quote.rs`.
Their SHA-256 values are respectively
`727e5b12a8a2e0b8a81be59b86ccb5252f88b1f66c64ca1cbc05ec71448f44df`
and `bb9156522ea47140e52e309b501ee3222ed5466fb8b33a779a31566e184fad8c`.

The parser hunk applied without fuzz to a copy of the stage parser. The
primed parser SHA-256 is
`5c4664c7c3034084d80073360836f496cf0c42675d513d3366ecfc4b7c103dc9`;
the PRE-cache parser is
`9f9fa318b874e90fedc4831c396d5c862888dd47e98f0ea73eb44ea11e61bf6d`.
The full parser diff contains only these two lines, present in the primed side:

```python
        for byte in _rust_url_dict_fromkeys(bs):
            quoter(byte)
```

Thus PRE-cache retains the current guard checks and isolates the effect of
adding cache priming. The effect includes a state transition: once a primed
call populates the cached `_Quoter` for a safe value, the current guard's
`_rust_url_dict_len(quoter.__self__) == 0` check fails on later calls for that
safe value. Those calls take the original Python path. In the PRE-cache arm,
the native route leaves that cache empty, so later eligible calls continue to
use it. The measured difference therefore includes both priming work and the
loss of later native calls; it is not a microbenchmark of the loop alone.
`_Quoter` and its cache are private `urllib.parse` implementation details,
although code can still observe the cached object through the private factory.
The priming change aims to preserve that internal state; these measurements
address its workload cost and do not assert that the cache is a public API.
Both overlays copy the stage `urllib/*.py` files and load the
same standalone extension at the same path, SHA-256
`b1ab627f758d778087fb2c8e8e8df0835396e9b9c8d3db45550c7ca74710d617`.
Import probes confirmed each parser path, the common extension path, and
`quote_from_bytes(b"x y", safe=b"/") == "x%20y"`. `otool -L` lists only
`/usr/lib/libSystem.B.dylib` for the extension.

The following exact command templates ran in the assigned worktree, each
wrapped with `/usr/bin/time -l -o <local log>`. `SOURCE` and `NATIVE` are
subdirectories of the ignored work area above. `LOCKED_LLVM` is
`/Users/josh/d/python-build/.cache/llvm/toolchains/23.1.2-d7c26fc6177e42842e2d1ffaad31aec057c56a924392b1a23d830abe2c5d53b1`.

```text
rustup run nightly-2026-09-15 rustc --edition=2024 --crate-type=staticlib -C opt-level=3 -C panic=abort --target=aarch64-apple-darwin SOURCE/Modules/_rust_url_quote/quote.rs -o NATIVE/libquote_ascii.a
LOCKED_LLVM/bin/clang -O3 -fPIC -mcpu=apple-m1 -mmacosx-version-min=26.0 -isysroot /Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX26.5.sdk -I /Users/josh/d/python-build/rust-cpython/stage/include/python3.16 -c SOURCE/Modules/_rust_url_quote/module.c -o NATIVE/module.o
LOCKED_LLVM/bin/clang -bundle -undefined dynamic_lookup -mmacosx-version-min=26.0 -isysroot /Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX26.5.sdk NATIVE/module.o NATIVE/libquote_ascii.a -o NATIVE/_rust_url_quote.cpython-316-darwin.so
```

| Build command | Wall s | User s | System s | Peak RSS B | Swaps |
| --- | ---: | ---: | ---: | ---: | ---: |
| rustc archive | 0.63 | 0.06 | 0.14 | 101,482,496 | 0 |
| Clang C compile | 0.47 | 0.06 | 0.10 | 54,165,504 | 0 |
| Clang bundle link | 0.49 | 0.08 | 0.14 | 35,176,448 | 0 |

## Complete workload measurement

The runner is `rust-cpython/experiments/url-quote-cache-cost-20260925.py`;
compact raw outcomes are in `data/url-quote-cache-cost-20260925.json`. Each
child used the accepted stage interpreter with `-B`,
`PYTHONDONTWRITEBYTECODE=1`, `PYTHONHASHSEED=1`, and
`PYTHONPATH=SIDE:NATIVE:ROOT`. Neither overlay had `__pycache__` before or
afterward, so both parsed source at each fresh import. The complete command
was `-m benchmarks.workloads.catalog_url_breadth TASK --iterations N`, with
N = 500 search-form or 1000 request-path operations. Pair order alternated
PRE/primed, primed/PRE, PRE/primed. The runner used `os.wait4` for external
monotonic wall, direct-child kernel user/system CPU, lifetime peak RSS, and
swap count; these tasks launched no descendants. Host load, swap, and top CPU
processes were sampled outside each pair. There was no in-process profiler.

Every attempt completed and returned input digest
`7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f`.
Every search-form output was
`a56d64f19accb1be3bb302cc60f406928d15182828c2b7e975e957d503dc1f22`;
every request-path output was
`52db5e5b89587be9b6690dde7ffccaf709c6c2592b31f881c05354d1475d2eff`.
The raw file identifies all 36 timed attempts across three comparisons and
their order, CPU, wall, RSS,
swaps, and exact digest outcome.

| Task | PRE wall median s | Primed wall median s | PRE CPU median ms/batch | Primed CPU median ms/batch | Paired wall ratios | Paired CPU ratios |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Search form | 1.381 | 1.619 | 2.173 | 2.517 | 1.135, 1.114, 1.173 | 1.144, 1.178, 1.152 |
| Request path | 0.633 | 0.667 | 0.394 | 0.423 | 1.042, 1.097, 1.061 | 1.020, 1.080, 1.076 |

An untimed one-batch native-call count used the same extension and each
overlay. After importing the workload, it cleared `_byte_quoter_factory` and
wrapped `_rust_url_quote.quote_bytes` to count calls by normalized safe bytes.
The complete output digests remained equal. PRE-cache made 104 native calls
for safe `b''` and 78 for safe `b' '` in search, and 32 for safe `b'/'` in path.
The primed route made **one** native call for each of those safe values; later
eligible calls found the quoter cache nonempty and took Python fallback.

An untimed repeat also recorded the input lengths of every PRE-cache native
call in one complete batch. These are the eligible call lengths when repeated
native dispatch remains active. Search had 182 calls: min 3, median 14,
max 2459 bytes; 128 were under 16, 46 were 16–63, 2 were 64–255, and 6 were
at least 256. Request path had 32 calls: min 8, median 15, max 17 bytes;
30 were under 16 and 2 were 16–63. The primed side saw only its first use
per safe value (search lengths 36 and 55; path length 10). This distribution
does not support adding a general length threshold without new paired work:
most eligible calls in these tasks are short, and a threshold at 16 bytes
would exclude most of them.

## Same-interpreter comparison to pure pinned parser

A third overlay copied the pure accepted stage `urllib/*.py` source; its
`parse.py` SHA-256 is
`178fce6bb504b9e544ac22015778554234c63865d94374913f988bb731e0d825`.
It used the same executable, worktree, task commands, source-only bytecode
policy, environment, `wait4` accounting, and three serial counterbalanced
pairs per task. The shared extension remained on `PYTHONPATH` for both arms;
the pure parser did not import it. All 12 primed-versus-pure and 12
PRE-cache-versus-pure attempts returned the exact input/output digests above.
Their raw outcomes and host snapshots are nested in the same JSON evidence.

| Comparison, candidate/pure | Search paired wall ratios | Search paired CPU ratios | Path paired wall ratios | Path paired CPU ratios |
| --- | --- | --- | --- | --- |
| Primed | 1.050, 1.089, 1.093 | 1.088, 1.090, 1.097 | 1.102, 1.109, 1.112 | 1.119, 1.136, 1.138 |
| PRE-cache | 0.963, 0.939, 0.957 | 0.959, 0.944, 0.954 | 1.067, 1.081, 1.066 | 1.060, 1.097, 1.059 |

The primed route's median paired CPU per complete batch was 2.095 ms versus
1.909 ms for pure search, and 0.291 ms versus 0.256 ms for pure path. The
PRE-cache route's median paired ratios were 0.954 CPU for search and 1.060
for path. The pure comparison therefore shows that cache priming removes the
small diagnostic search benefit of the PRE-cache route and adds more path
cost. These groups ran later under different host conditions; ratios compare
only within their own pairs.

The PRE-cache overlay retains an unused `dict.fromkeys` snapshot and its old
comment, while the final revised patch removes them. Its runtime quotation
branch is the same; the PRE-cache timing is a diagnostic proxy for the final
revision, not an installed-build measurement of its exact bytes.

For primed versus pure, one-minute load was 7.90 before and 8.07 after;
OrbStack Helper was at about 404–407% CPU. For PRE-cache versus pure, load
was 7.31 before and 7.10 after, and OrbStack was at about 310% CPU. System
swap used remained 243.88 MiB. This host contention prevents a publishable
speed verdict despite consistent kernel CPU direction.

Peak root RSS ranged from 34.3 to 34.8 MB across all runs, without a clear
side separation; every `wait4` swap count was zero. At the start,
one/five/fifteen-minute load was `10.77/6.58/4.90` and OrbStack Helper was
at `807.9%` CPU. At the end, load was `13.26/7.34/5.20` and OrbStack Helper
was at `866.6%` CPU. System swap used stayed `243.88 MiB`. The wall ratios
are exposed to contention. The consistent CPU direction is a useful warning
about priming, not a quiet-host qualification or integrated product result.

No tests, formatter, linter, hook, dependency addition, or lane commit ran.
The main stage and other worktree build outputs were untouched.
