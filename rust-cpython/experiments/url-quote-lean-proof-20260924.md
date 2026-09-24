# Lean Rust URL quotation proof

## Question and boundary

Can the guarded CPython 3.16 `urllib.parse.quote_from_bytes` proof avoid its
temporary Python bytes buffer and most of the Rust runtime footprint? This is
an isolated overlay, not a product patch. Run
`url-quote-lean-proof/build.py` with the pinned GIL-enabled no-Rust CPython
3.16 control, then put its `.work/overlay` first on `PYTHONPATH`. The builder
checks the installed `urllib/parse.py` SHA-256 before copying it. It inserts
the identical guarded Python branch used by `url-quote-proof`: only exact
`bytes` input, normalized exact `bytes` safe, and length below 200,000 reach
the extension after the original validation and early returns. Its overlay
parse SHA-256 is the same as that proof,
`8e29cff7399e7bae9e243bcc022afa43d73ad85912b9468b1e3cc73875079576`.

`quote.rs` uses `#![no_std]` and no dependency. The first Rust pass counts
escaped ASCII bytes. C checks that the result lies in `[0, 3 * input_len]`,
allocates `PyUnicode_New(output_len, 127)`, and passes its one-byte payload to
the second Rust pass. The second return must equal `output_len`. Both passes
hold borrowed buffers from live exact Python bytes objects; no Python callback
can mutate them. Rust returns `-1` on an invalid pointer, length, or fill
capacity, including a subtraction-underflow guard if the supplied capacity
is smaller than bytes already written. Its panic handler calls `abort` so no panic unwinds across the C
ABI; an abort would indicate a broken Rust invariant, not a recoverable
quotation error. The C wrapper maps Rust contract failures to Python
`RuntimeError` and CPython allocation failure to its normal exception.

The two-pass design scans short inputs twice and constructs the allowed table
twice. It removes the temporary bytes allocation and ASCII decoding. It also
avoids calling a Python API while the Unicode payload is uninitialized.

## Evidence

The copied differential harness passed 2,177 public `quote_from_bytes`,
`quote`, and `quote_plus` cases against the installed control, including every
byte value, safe normalization, subclasses, invalid inputs, and the guarded
length boundary. It observed one native hit for `quote(b'a b', safe='')` and
none for an already-safe or bytearray example. The unchanged CPython
`-m test test_urlparse test_urllib -j1` passed 182 tests, 7 skipped. One
complete registered `catalog_url_normalize` operation, with 48 URLs and 48
keys, returned input digest
`7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f`
and output digest
`a6fedf33e0fd5e72b79af8d77499b9a7bb8e8d53491955f2e554570679e04941`.
That run was a semantic check, not a timing comparison.

| `/usr/bin/time -l` command | User CPU | System CPU | Peak RSS | Swaps |
| --- | ---: | ---: | ---: | ---: |
| Build extension | 0.22 s | 0.18 s | 101,482,496 B | 0 |
| Differential public cases | 0.10 s | 0.01 s | 30,162,944 B | 0 |
| CPython URL suites | 0.53 s | 0.15 s | 57,507,840 B | 0 |
| One catalog URL operation | 0.05 s | 0.03 s | 25,739,264 B | 0 |

These commands totaled 1.27 user plus system CPU seconds; their largest
measured peak RSS was 101,482,496 bytes. The build and differential results
were rerun after the capacity guard was hardened; the CPython suites and
catalog operation were run before that defensive change. `/usr/bin/time -l` includes waited
child CPU in command totals; maximum RSS is a process maximum, not a sum of
simultaneous processes. All generated files stayed under this worktree's
ignored `.work/`. No paired benchmark, formatter, linter, or hook ran.

The four source files total 10,810 bytes: `quote.rs` 2,515, `module.c` 2,133,
`build.py` 3,104, and `check.py` 3,058. The intermediate static library is
6,277,680 bytes. The unstripped extension is **50,712 bytes**, SHA-256
`74feaae8a1f52c735a61b94a4abe82daf2f65c4896434aca2b874200ce93a344`.
The prior extension was 1,473,544 bytes, so this variant removes 1,422,832
installed extension bytes (96.6%). `otool -L` reports only
`/usr/lib/libSystem.B.dylib`; `nm -gU` shows defined `_quote_ascii` and
`_PyInit__rust_url_quote` symbols. The build used pinned nightly Rust
2026-09-15, locked clang 23.1.2, and Xcode SDK 26.5.

## Decision

**Inconclusive as a keep candidate.** The semantic and installed-size results
support a matched full-workload comparison. This lane did not measure paired
wall time, process CPU, or peak and retained memory against the control or
the prior guarded proof. The earlier proof's 19.3% paired wall gain came with
a 3,194,880-byte peak RSS increase; this variant must clear that resource
regression without losing the useful latency gain before promotion.
