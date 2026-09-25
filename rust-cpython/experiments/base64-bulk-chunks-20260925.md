# Base64 bulk loop: optional source patch

The pinned Rust-for-CPython source is commit `b812b4a7b9efaca46b98544a8633b7d7e454166b`. Its `Modules/_base64/src/lib.rs` has SHA-256 `3bcc6396bc10c4ae3022b05d7093751428414c0b6c694ee9bace47b725218a17`. The optional [patch](base64-bulk-chunks-20260925.patch) has SHA-256 `48f02902978e7ed186e76eb9e677688442efd2baa30b89f9cf1b694394eb42c7` and produces source SHA-256 `712afb7f0d258f68acc7ec1bf38a0501ea6fd9ad5f8fff00803a1214731b357a`. It is authored for this experiment from the pinned source and is not in `patches/manifest.json`.

The existing encoder uses indexed input and output slices for each complete 3-byte group. In an isolated `rustc 1.100.0-nightly (574ff7d98 2026-09-14)` AArch64 `-O -C target-cpu=apple-m1` assembly probe, the hot loop retained three output bounds branches per group and one shared `panic_bounds_check` cold target. The candidate uses `chunks_exact(3).zip(chunks_exact_mut(4))`; its hot loop has no bounds branches, and the remaining cold bounds checks serve the unchanged 1- or 2-byte tail. Both probes used the same exported raw pointer wrapper to keep the encoder reachable and force `encoded_output_len(input_len)` for the output slice. Assembly was generated with `--crate-type lib --emit asm`; no benchmark was run.

The actual call site allocates `ceil(input_len / 3) * 4` output bytes before calling `encode_into`. Therefore every complete input group has a complete output group, `zip` processes all complete input groups, and the unchanged tail writes at the same offsets. This is a source-level argument for equal bytes, not a runtime correctness result. The patch was applied to a fresh copy of the pinned file with `patch --dry-run -p1` followed by `patch -p1`; the resulting bytes matched the candidate source hash above.

To repeat the codegen probe, use two copies of the verified pinned file, applying the digest-checked patch to only the candidate. For each copy, extract the text from `const PAD_BYTE:` up to `struct BorrowedBuffer`, then append this wrapper and compile with the pinned nightly:

```rust
#[unsafe(no_mangle)]
pub unsafe extern "C" fn encode_into_raw(input: *const u8, len: usize, output: *mut u8) -> usize {
    let input = unsafe { std::slice::from_raw_parts(input, len) };
    let output = unsafe { std::slice::from_raw_parts_mut(output, encoded_output_len(len).unwrap()) };
    encode_into(input, output)
}
```

```sh
rustc +nightly-2026-09-15 --crate-type lib -O -C target-cpu=apple-m1 --emit asm -o encoder.s encoder.rs
```

Existing quiet-host evidence puts direct Rust at 563.03 µs and direct `binascii` at 381.57 µs per 1 MiB. Removing three repeated checks could close a material part of that gap, and a large-input public guard would amortize its Python call cost. The public `Lib/base64.py` still calls `binascii.b2a_base64`, while Rust only supports standard padded unwrapped output. The prior guarded small-input route was slower, so that route remains rejected. This patch is **inconclusive** until a quiet-host direct bulk comparison shows Rust beating C by more than noise and a separate public route preserves all options and replacement behavior. Do not promote it from this codegen result alone.

No CPython build, runtime test, timing measurement, formatter, linter, or hook ran in this lane.
