# Optional Rust URL unquote source patch, 2026-09-25

## Selection and boundary

`python3 rust-cpython/build.py build` retains the existing three-patch quote-only source. `python3 rust-cpython/build.py build --url-unquote` adds `0004-rust-url-unquote.patch` after those patches. The optional patch changes only the pinned Rust-for-CPython `Lib/urllib/parse.py`, `Modules/_rust_url_quote/module.c`, and `Modules/_rust_url_quote/quote.rs`. Existing zlib mode flags remain independent and mutually exclusive with one another. The CPython 3.14.6 product source and build are outside this lane.

The patch is named and SHA-256 checked in `patches/manifest.json`. `build.py` validates the optional mode field, checks the pinned source and Cargo lock, checks and applies each selected patch, and requires a successful reverse check plus a failed forward check. The build report records the manifest digest, selected patch records, and `url_unquote` boolean. `test()` reconstructs the selected patch set from that report before running tests; it does not silently switch an opt-in build back to the default selection. Reports from builds made before this manifest change fail the identity check until rebuilt, which is expected fail-closed behavior.

The patch follows the measured proof's exact-str, exact-codec, UTF-8 replacement guard and C-owned decoding boundary. The only source difference from the proof's `quote.rs` is a top doc comment describing the installed code in domain terms; executable Rust code matches the proof. No dependency, toolchain, source pin, or production target changed.

## Fresh-source evidence

The pinned 44,210,863-byte source archive was read from a verified cache and SHA-256 checked as `965dbc9c847b0ed779a16134495b8690c9fc957996d8bcbb83c47089d4e81467`. Separate fresh extractions under `/private/tmp/python-build-url-unquote-validate-20260925a/` were patched with the default and opt-in selections outside repository Git discovery. Both applied all selected patches with forward and reverse checks. An inventory of file bytes and symlink targets found exactly the three intended paths different. A final fresh extraction independently accepted the final patch and manifest after the source comment edit. Python AST parsing and manifest digest validation passed; no compiler, test suite, formatter, linter, hook, or full build ran.

| Source path | Default SHA-256 | Opt-in SHA-256 |
| --- | --- | --- |
| `Lib/urllib/parse.py` | `85ac4db38a30e3b12dd78ff0a5b83baa61caedebc3a44c33cd45c85c3279acee` | `ad11741ef88e9b7175ef0e1ffb311fdee865c073194743e08eb61adee828f4dd` |
| `Modules/_rust_url_quote/module.c` | `727e5b12a8a2e0b8a81be59b86ccb5252f88b1f66c64ca1cbc05ec71448f44df` | `ffd925c31613f4be971e02afa29c891b454e0d348d62d38bf892a54db8259864` |
| `Modules/_rust_url_quote/quote.rs` | `bb9156522ea47140e52e309b501ee3222ed5466fb8b33a779a31566e184fad8c` | `7fd630546e5883e9c5c4fbfa23b2bf7b7a5411da42b866436605c2cea83a2e32` |

`0004-rust-url-unquote.patch` SHA-256: `27c0e4c21be013830d253215db25a1f3f04566755a2d5e19e879977ceae033a7`.

The five timed preparation and validation commands recorded **4.39 user + 6.55 system = 10.94 CPU seconds**, 105,086,976 bytes maximum reported process RSS, and zero swaps. Their unique raw logs and `/usr/bin/time -l` records are under ignored `rust-cpython/logs/url-unquote-*-20260925a.*` in this worktree. A preliminary broad read-only cache search was not timed and is excluded from that total. The resource figures are kernel-accounted command process-tree totals; maximum RSS is a lifetime process peak, not unique memory.

## Remaining gates

Before promoting the optional mode, build both selections with the locked macOS toolchain; check that installed parser and extension identities match their source selection. Differentially compare public `unquote`, `unquote_plus`, and `parse_qsl` behavior against the pinned no-Rust interpreter across escaped bytes, malformed escapes, mixed non-ASCII text, subclasses, bytes and bytearray, custom codecs and errors, no-percent identity, and long inputs. Run focused `test_urlparse` and `test_urllib` suites. The native eligible path bypasses the parser's private lazy `_hextobyte` initialization and replaceable private globals; that private-state behavior differs from the Python path. Exact codec and error-string guards also leave codec dispatch behavior to verify. The earlier matched LLVM complete-task speed result supports this optional source candidate, while broad semantic qualification remains open.
