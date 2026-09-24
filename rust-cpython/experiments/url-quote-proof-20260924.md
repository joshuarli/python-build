# Guarded Rust URL quotation proof

## Question and boundary

Can a std Rust byte scanner preserve pinned CPython 3.16 `urllib.parse.quote`
behavior inside the registered catalog URL task? This proof is an isolated
overlay, not a product patch. Run `url-quote-proof/build.py` with the pinned
Rust fork interpreter, then put its ignored `.work/overlay` before the checkout
on `PYTHONPATH`. The builder checks the installed `urllib/parse.py` SHA-256
before copying the package and inserting a guarded call. The input interpreter is
`/Users/josh/d/python-build/rust-cpython/stage/bin/python3.16`, SHA-256
`6eeeb64b9eb161d4d5edb9200e79146dabd8acc0f73fcdca48417d0e3c9531bd`;
its installed parse source is SHA-256
`178fce6bb504b9e544ac22015778554234c63865d94374913f988bb731e0d825`.

The Python path preserves `bytes`/`bytearray` validation, empty return,
non-ASCII removal from `safe`, and the already-safe return. It calls the
extension only after those exits for exact `bytes` input, exact normalized
`bytes` `safe`, and length below 200,000. Other inputs and the large-input
chunking path use the installed mapping implementation. The C wrapper checks
exact argument types and length again. It borrows live bytes buffers, allocates
at most three output bytes per input byte, invokes one Rust `extern "C"`
function, decodes only the written ASCII output, and releases the temporary
buffer. The Rust function uses no CPython API, global mutable state, or new
dependency. Its allowed set is ASCII letters, digits, `_.-~`, and normalized
`safe`; escapes use uppercase hex. The experiment uses pinned nightly Rust
2026-09-15, locked clang 23.1.2, and Xcode SDK 26.5.

## Correctness evidence

`/usr/bin/time -l env PYTHONPATH=rust-cpython/experiments/url-quote-proof/.work/overlay
<control> rust-cpython/experiments/url-quote-proof/check.py` passed 2,177
differential public `quote_from_bytes`, `quote`, and `quote_plus` cases. They
cover every byte value, reversed byte order, safe sets including NUL, DEL,
non-ASCII values, string and iterable normalization, empty/already-safe input,
199,999/200,000-byte boundary cases, invalid inputs, and byte subclasses.
Return values and exception class/message matched the installed source. An
observed `quote(b'a b', safe='')` reached the Rust wrapper once; the bytearray
and already-safe examples did not. The check took 0.11 user + 0.01 system CPU
seconds, 30,310,400 bytes peak RSS, zero swaps.

The unchanged CPython `-m test test_urlparse test_urllib -j1` passed: 182 tests
run, 7 skipped. `/usr/bin/time -l` reported 0.49 user + 0.11 system CPU
seconds, 57,589,760 bytes maximum RSS, zero swaps. One complete registered
`catalog_url_normalize` batch through the public application functions
returned the locked input digest
`7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f`
and output digest
`a6fedf33e0fd5e72b79af8d77499b9a7bb8e8d53491955f2e554570679e04941`.
That process took 0.03 user + 0.01 system CPU seconds, 25,509,888 bytes
maximum RSS, zero swaps. Its short elapsed value is a correctness run, not a
performance comparison.

The final build took 0.21 user + 0.14 system CPU seconds, 114,278,400 bytes
maximum RSS, zero swaps under `/usr/bin/time -l`. The unstripped extension is
1,473,544 bytes; the intermediate Rust static library is 18,688,744 bytes
and remains ignored in this worktree. `nm -gU` shows defined
`_quote_ascii` and `_PyInit__rust_url_quote` symbols in the arm64 Mach-O
bundle. `otool -L` shows only `/usr/lib/libSystem.B.dylib` as a dynamic
dependency; there is no dynamic Rust or other third-party library. This
identity check took 0.02 user + 0.04 system CPU seconds, 5,652,480 bytes
maximum RSS, zero swaps. Two initial compiler failures were corrected: edition
2024 requires `#[unsafe(no_mangle)]`, and locked clang needs the Xcode SDK
sysroot for C headers. Including those failed commands and the subsequent
rebuild, the recorded commands consumed about 1.9 user+system CPU seconds;
the largest measured peak RSS was 114,360,320 bytes. `/usr/bin/time -l`
accounts command descendants' CPU through normal wait accounting; maximum RSS
is a command maximum, not simultaneous tree memory. All commands reported zero
swaps. No formatter, linter, hook, or comparative benchmark ran.

## Decision

**Inconclusive for keeping the Rust path.** Semantics and complete-batch
reachability are proven, but no paired timing, CPU, or memory comparison has
been made. The coordinator will schedule that comparison on a quiet host.
The headroom report found that, over 100 profiled batches, 9,200 of 9,600
guarded calls had at most 17 input bytes. If this proof is slow, first
investigate per-call construction of the 128-entry Rust allowed table and the
temporary Python bytes allocation before Unicode decoding. A 1.47 MB extension
also has an installed-size cost.
Do not promote the path without a full-workload gain beyond measured noise
and resource qualification.
