# Locked source archive Base64 workload

The [workload](base64-archive-workload-20260925.py) encodes the exact pinned Rust-for-CPython source archive through the public `base64.b64encode` API. It first verifies the archive's 44,210,863 bytes and SHA-256 `965dbc9c847b0ed779a16134495b8690c9fc957996d8bcbb83c47089d4e81467`. It then reads 65,536-byte chunks, Base64 encodes each chunk separately, and hashes a compact ASCII JSON line for each chunk. Each line has `base64`, zero-based `chunk`, byte `offset`, and `raw_bytes` fields, sorted by key, with no spaces and one trailing newline. The 58,991,181 output bytes are hashed without retaining or writing the full output. The script rejects any output digest other than `108345723516149b47babd0be812f64ff40a0fea49cea23090b68828f9cde835`.

The complete input makes 675 public calls: 674 calls with 65,536 bytes and one with 39,599 bytes. All are above the optional `binascii` route's 4,096-byte threshold. The pinned public `base64.py` forwards these default-alphabet, padded, unwrapped calls to `binascii.b2a_base64(..., newline=False)`, so a candidate interpreter with that optional route installed can exercise it without changing the workload. The fixed output identity checks the entire sequence and its chunk boundaries, offsets, and lengths. The archive's own compressed bytes are the input; the workload does not unpack the TAR.

## Reproduce the control pass

The original cache object was absent, so this lane downloaded the URL already recorded in `rust-cpython/sources.lock.json` into ignored worktree scratch. No source pin or dependency changed. From this worktree root on macOS:

```sh
archive=rust-cpython/work/base64-archive-workload-20260925/cpython-source.tar.gz
mkdir -p rust-cpython/work/base64-archive-workload-20260925
curl --fail --location --retry 3 \
  --output "$archive" \
  https://codeload.github.com/Rust-for-CPython/cpython/tar.gz/b812b4a7b9efaca46b98544a8633b7d7e454166b
shasum -a 256 "$archive"
wc -c "$archive"
/usr/bin/time -l \
  /Users/josh/d/python-build/rust-cpython/stage/bin/python3.16 -I -S -B \
  rust-cpython/experiments/base64-archive-workload-20260925.py "$archive"
```

Check that `shasum` prints `965dbc9c847b0ed779a16134495b8690c9fc957996d8bcbb83c47089d4e81467` and `wc` prints `44210863`. The script also enforces both values before encoding. The staged interpreter executable has SHA-256 `6eeeb64b9eb161d4d5edb9200e79146dabd8acc0f73fcdca48417d0e3c9531bd`; its `base64.py` has SHA-256 `93319e370390777e2b0a14dcb02b53d61e1bc83719c088e760eb5ab74eafa978` and installed `binascii` extension has SHA-256 `8d5d97f4e81f4db5baf1a16eb0eb81e3d3951248a56aa4b959a41537b3004494`. `-I -S -B` isolates imports, skips site startup, and disables bytecode writes.

## Control result and limits

The final control run exited zero and reported 675 chunks, 44,210,863 input bytes, 58,949,616 Base64 bytes, and the fixed 58,991,181-byte JSON-line digest. Inside Python, after imports, the identity check plus encoding used 0.123946333 s wall, 0.115713 s user CPU, and 0.007707 s system CPU; its peak RSS was 27,181,056 bytes. `/usr/bin/time -l` measured the whole process at 0.16 s wall, 0.13 s user CPU, 0.02 s system CPU, 27,213,824 bytes maximum resident set, and zero swaps. These numbers establish that the control workload completes cheaply; they are not a route speed comparison. The run used the original staged `binascii`, with no optional route installed. Raw identities, the exact command vector, and resource fields are in [compact evidence](data/base64-archive-workload-20260925.json).

No paired or timed route arms were run while the host was busy with another lane's build. A future qualification should use this unchanged workload and archive on matched control and route interpreters, check both exact output digests, and account for process CPU and memory. No test suite, formatter, linter, hook, dependency edit, commit, or push was performed here.
