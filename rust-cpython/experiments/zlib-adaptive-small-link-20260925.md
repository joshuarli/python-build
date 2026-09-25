# Adaptive zlib private-link size proof, 2026-09-25

**Size verdict: viable on macOS arm64.** An opt-in
`--zlib-adaptive-small` recipe keeps the same 8 KiB adaptive source patch,
pinned zlib-rs 0.6.7 source and Cargo feature recipe, optimizer, and `-lz` ordering as
`--zlib-adaptive`. It changes only the generated zlib extension link rule by
adding `-Wl,-dead_strip -Wl,-exported_symbol,_PyInit_zlib`. The existing
`-Wl,-export_dynamic` remains. The measured signed, stripped extension is
1,054,736 bytes smaller, and code and constants shrink. The link-only pair
did not establish semantic or speed qualification. A fresh full build below
succeeded and passed installed import and round-trip identity checks. This is a
size and symbol result, not a broad semantic, memory, or speed qualification.
No separate tests or published timing comparison ran; the unrelated container
was CPU-heavy. Linux needs a separate linker recipe and evidence.

## Reproduce the link pair

The source is the completed `--variant zlib-adaptive --zlib-adaptive` build in
`/Users/josh/d/python-build-exp-zlib-adaptive-20260925`. The three copied
inputs persist in this worktree under `rust-cpython/work/zlib-size-link/`:
They came from, respectively,
`rust-cpython/work/variants/zlib-adaptive/build/Modules/zlibmodule.o`,
`rust-cpython/work/variants/zlib-adaptive/zlib-candidate-target/release/libz_rs.a`,
and `rust-cpython/stage-zlib-adaptive/lib/python3.16/lib-dynload/zlib.cpython-316-darwin.so`
under that source worktree.

| Input | Bytes | SHA-256 |
| --- | ---: | --- |
| `zlibmodule.o` | 193,408 | `8af5449e5b12743651cf9854a2dea16eadc6422c7e798ac2458b1c369f372c0a` |
| `libz_rs.a` | 18,950,392 | `c6ca1298a9e48291b6387cecb0a112f761330f94c771bc330405cde037484f06` |
| `original.so` (installed adaptive zlib) | 1,676,264 | `d09e1617974e142622921c2467257e865540115585d593f51845bfd4a9899403` |

The official locked LLVM 23.1.2 `clang` SHA-256 is
`f8fa7184dab7d8fa7f6af268a6f1b3aa3d2e598d0cca04dc68447b4c0ca58d8e`;
`llvm-strip` is
`c8ec9c4901ce23a0b48a8eb5588ec11c9a3ac0d40074f844336b5e835592eb13`.
The SDK is Xcode MacOSX 26.5 at
`/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk`,
with deployment minimum 26.0. Run from the directory holding the copied
inputs. Set `SDKROOT` to that SDK path. Set `CLANG` to the locked
`/Users/josh/d/python-build-exp-zlib-adaptive-20260925/.cache/llvm/toolchains/23.1.2-d7c26fc6177e42842e2d1ffaad31aec057c56a924392b1a23d830abe2c5d53b1/bin/clang`.
Its original final PGO link command is recorded
in `rust-cpython/logs/variants/zlib-adaptive/cpython-build.log` at line 1761.
The copied-object control and candidate effective commands were:

```sh
"$CLANG" -bundle -undefined dynamic_lookup -mmacosx-version-min=26.0 -mmacosx-version-min=26.0 -flto=thin -Wl,-export_dynamic -Wl,-object_path_lto,control.so.lto -g zlibmodule.o -lz libz_rs.a -o control.so
"$CLANG" -bundle -undefined dynamic_lookup -mmacosx-version-min=26.0 -mmacosx-version-min=26.0 -flto=thin -Wl,-export_dynamic -Wl,-object_path_lto,candidate.so.lto -g -Wl,-dead_strip -Wl,-exported_symbol,_PyInit_zlib zlibmodule.o -lz libz_rs.a -o candidate.so
```

The `-object_path_lto` destinations and output names changed only to keep the
two links separate. For packaging comparison, copy each `.so`, run the same
locked `llvm-strip --strip-debug` on each copy, then
`codesign --force --sign -` on each. `codesign --verify --strict` succeeded
for both copies. `binascii` was untouched; the adaptive stage's binascii SHA
is `2b16117ae242c76c7caf112296944d9d2934d0ef0c3878786d8e0623c0135953`
and its only non-System dynamic dependency is `/usr/lib/libz.1.dylib`.

## Bytes and Mach-O evidence

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Matched control, unstripped | 1,675,928 | `d5fc7f1b6f44e25a2f9a0599bdc41d65090b3e13ddc7dd2f409d61fa14906827` |
| Private/dead-strip candidate, unstripped | 507,072 | `7de8a82e4aa2ad56f135bb544feefedeaf027339b123077f4e10562e2d232336` |
| Matched control, stripped and signed | 1,538,000 | `f36ab656cb9035c1f01062e6a6105bbe12dfe5ceaa43c60747f2b001fa297bc1` |
| Candidate, stripped and signed | 483,264 | `e78f0486dd0a3222729a41efe299d8515a2b54880d13a4eb4db4bde817842fd0` |

| `size -m` field | Control bytes | Candidate bytes | Change |
| --- | ---: | ---: | ---: |
| `__TEXT` file segment | 999,424 | 327,680 | −671,744 |
| `__text` section | 713,852 | 243,196 | −470,656 |
| `__TEXT,__const` | 109,784 | 30,232 | −79,552 |
| `__DATA_CONST` file segment | 49,152 | 16,384 | −32,768 |
| `__DATA_CONST,__const` | 38,568 | 7,976 | −30,592 |
| `__DATA` file segment | 16,384 | 16,384 | 0 |
| `__DATA,__data` | 5,368 | 5,168 | −200 |
| `__LINKEDIT` file payload, unstripped | 610,968 | 146,624 | −464,344 |
| `__LINKEDIT` file payload, stripped and signed | 473,040 | 122,816 | −350,224 |

`otool -l` reports 12,429/3,354 unstripped symbols and 3,586/1,043
stripped symbols (control/candidate). The unstripped string tables are
274,280/83,352 bytes. The signed, stripped linkedit starts at offsets
1,064,960/360,448 and its code-signature payloads are 21,216/19,168 bytes.
The candidate has exactly one global definition, `_PyInit_zlib`, before and
after stripping; the control has 1,871. `nm -a` still finds local definitions
of `_python_build_rs_inflateInit2_`, `_python_build_rs_inflate`, and
`_python_build_rs_inflateEnd`. No unprefixed zlib function is defined. The
undefined platform imports include `_inflateInit2_`, `_inflate`,
`_inflateEnd`, `_inflateCopy`, and `_inflateSetDictionary`. `otool -L`
retains `/usr/lib/libz.1.dylib` version 1.2.12 and
`/usr/lib/libSystem.B.dylib`; both signed copies passed strict verification.

## Resource accounting and limits

`/usr/bin/time -l` measured each waited linker/tool process tree; its peak
RSS is the largest process peak, not aggregate concurrent RSS. Footprint is
macOS charged memory. No process-count sampler ran. Host swap was 243.88 MiB
before and after; every recorded command had zero process swaps. Attempts
are preserved here, including two failed setup attempts:

| Attempt | Outcome | Wall s | User s | System s | Peak RSS B | Peak footprint B |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| link-001 | Wrong copied toolchain path; executable absent | 0.00 | 0.00 | 0.00 | 999,424 | 819,368 |
| link-002 | Candidate link failed: SDK absent, `ld: library 'z' not found` | 0.15 | 0.03 | 0.04 | 14,974,976 | 2,785,760 |
| link-003 | Candidate link succeeded with `SDKROOT` | 0.29 | 0.19 | 0.09 | 74,465,280 | 2,966,008 |
| link-004 | Matched control link succeeded | 0.21 | 0.19 | 0.06 | 75,956,224 | 2,949,624 |
| strip-001 | Control `llvm-strip` succeeded | 0.03 | 0.00 | 0.00 | 8,290,304 | 4,768,104 |
| strip-002 | Candidate `llvm-strip` succeeded | 0.01 | 0.00 | 0.00 | 4,849,664 | 2,474,320 |
| sign-001 | Control ad-hoc sign succeeded | 0.01 | 0.00 | 0.00 | 7,536,640 | 3,408,136 |
| sign-002 | Candidate ad-hoc sign succeeded | 0.01 | 0.00 | 0.00 | 6,701,056 | 2,752,848 |

## Fresh isolated build

The exact command was
`/usr/bin/time -l -p python3.14 rust-cpython/build.py build --variant zlib-adaptive-small --zlib-adaptive-small`
from this worktree. Before it, `doctor` found a missing isolated LLVM/cache
and Cargo home. Attempt `build-001` failed before compilation in 0.62 s wall,
0.18 s user, 0.22 s system, 38,764,544 B peak RSS, 27,296,248 B peak
footprint, and zero process swaps. I then APFS-cloned the adaptive worktree's
verified 2.0 GiB `.cache` and 34 MiB private Cargo home into this worktree.
That short clone was not timed; its process resource use is missing. A second
`doctor` passed with zero problems. The SDK is 26.5 and Xcode is 26.6, matching
their distinct lock fields; no host or pin was changed.

Attempt `build-002` succeeded in 302.75 s wall, 702.63 s kernel user and
111.70 s kernel system. `/usr/bin/time -l` measured 1,758,838,784 B peak
reported RSS, 55,788,048 B peak footprint, and zero process swaps. It
covers the controller's waited children, but not simultaneous tree RSS;
process count was not sampled. Host swap remained 243.88 MiB and reported
free memory remained 84% before, during, and after. The PGO task was
`-m test --pgo -j 9`; no separate test command ran. The completed report is
in ignored `rust-cpython/results/build-zlib-adaptive-small.json`, with
configure, toolchain, patch, Makefile, archive, and installed identities.

The fresh source is pinned commit
`b812b4a7b9efaca46b98544a8633b7d7e454166b` from archive SHA-256
`965dbc9c847b0ed779a16134495b8690c9fc957996d8bcbb83c47089d4e81467`.
The patch manifest SHA-256 is
`a0da9732859fab4e95680e28a6cff95af99884f0a2031146436751f3bc1ba410`,
and the same 0001, 0002, 0003, and 0011 patches were selected as in the
adaptive stage. `Modules/zlibmodule.c` changed from
`36390fc1b0bdaf7da332d732c67cbe9669bd3f6e923a3e5810b4662159a0e20c`
to `8bcd620f2f12e826f0cc2b28639541ec3452e0220fc2dccd84c196c21c07534d`,
exactly the adaptive source hash. The new build's `libz_rs.a` SHA-256 is
`5d1d11d82de8e79fc7a7481915ae0aa5f02b7444510bd9ac76712961ec5882ca`
and size is 18,950,072 B. It differs by 320 B from the earlier archive while
keeping the same pinned source and Cargo features; generated archive bytes
are not being claimed reproducible across these separate builds.

The configured Makefile SHA-256 was
`a7d6d39661ec456a7c30bd330e795770ffe9f5a1e622dc1b9804695b3d648ed1`.
After binascii isolation it was
`b3ab4fc2c85b5af05da59a4edb122656de9a8f201a49fca9a992808cd07784e2`;
after the exact zlib rule rewrite it was
`8333e7756df3241a88ed9e28e5683b8a6f381c874bf4402699801dab1f474602`.
The final link in `rust-cpython/logs/variants/zlib-adaptive-small/cpython-build.log`
at line 1761 retains `-flto=thin -Wl,-export_dynamic -g`, `-lz` before the
static archive, and adds only `-Wl,-dead_strip
-Wl,-exported_symbol,_PyInit_zlib` to the zlib rule.

| Installed-stage comparison | Adaptive control | Adaptive small |
| --- | ---: | ---: |
| Unstripped bytes | 1,676,264 | 507,304 |
| Unstripped SHA-256 | `d09e1617974e142622921c2467257e865540115585d593f51845bfd4a9899403` | `8656483898cf0a631bc1a5c00beb306d8fb441fdf90fda609aa1aee4faf780af` |
| Signed, `llvm-strip --strip-debug` bytes | 1,538,000 | 483,264 |
| Signed, stripped SHA-256 | `a0692873f2027bdc940b42bc350653bda9efae8856ef8a95c0578b68f34c18fa` | `f16e4d7984943dd4ceee3dcc4ccb4c759a62322e1a4cd1952c675e7bbc88a308` |

The installed candidate has `__text` 243,196 B, `__TEXT,__const` 30,232 B,
and `__DATA_CONST,__const` 7,976 B, exactly the link-only candidate section
sizes. Its only global definition is `_PyInit_zlib`; the three prefixed Rust
inflate functions remain local. The five platform inflate references and
`/usr/lib/libz.1.dylib` load command remain, and no unprefixed zlib function
is defined. The builder loaded the installed extension and checked a
compress/decompress round trip, checksum identity, platform runtime version
1.2.12, and platform-only binascii linkage. Both installed-stage copies
passed `codesign --verify --strict` after the identical strip and ad-hoc sign
steps. The four strip/sign commands each took 0.01–0.02 s wall, had zero
process swaps, and peaked at 4,653,056/8,437,760/6,701,056/7,536,640 B
RSS for candidate strip/control strip/candidate sign/control sign respectively;
their kernel user and system times rounded to 0.00 s each.

The adaptive route still needs quiet-host semantic, CPU, memory, and paired
speed qualification before acceptance. This build gives no speed claim and
does not alter the production CPython 3.14.6 build.
