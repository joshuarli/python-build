# UUID constructor guard audit

The optional canonical UUID scanner now checks the module-visible `type`, `str`, `len`, `__import__`, `sys`, `UUID`, and `int_` bindings against their original values before trying native parsing. It also checks the current builtins `int` and `__import__`. A preloaded private module is ignored; after its first import, the scanner runs only while the same module remains in `sys.modules`. The imported `scan` must be a built-in function bound to that module and report the expected module name. Changed bindings use CPython's original text parser.

This closes two concrete bypasses in the previous patch: a changed `uuid.type` could raise before the original constructor touched it, and a caller could change both `uuid.int_` and `uuid._ORIGINAL_INT` so the old guard skipped the caller's conversion function. It also prevents a preloaded Python module named `_rust_uuid_canonical` from supplying a scanner result.

## Source and diagnostic evidence

- Pinned source: Rust-for-CPython `b812b4a7b9efaca46b98544a8633b7d7e454166b`, `Lib/uuid.py` SHA-256 `d8c8dbfaed0297e0a1aace22e19d298a8c86740725a1d598f128d333e91b84a4`.
- Previous patch SHA-256: `939dd73e59400cd19a06148805d8c9935fd84e84f41070a48aa87806b138f61b`. Updated patch SHA-256: `50f49664ff00ef4f99c268f4ae36bc7928d495499575258038e4ea38fc880f83`.
- The UUID hunk passed `patch --dry-run -p1` against a copied pinned source file. Applying it to that copy produced the same bytes as the authored overlay, SHA-256 `d32bd90c2e6afe9804e7be22b4fea56799c660e1f2bda149e6f722f06759e9d1`. `python3 -m py_compile` accepted the overlay.
- A local Python source-only diagnostic loaded the pinned and patched modules with a shadow `_rust_uuid_canonical` module already in `sys.modules`. Constructor result or exception matched for lowercase canonical, uppercase canonical, URN, and malformed text. The patched constructor ignored the shadow scanner.
- The same diagnostic installed throwing module-level `type`, `str`, and `__import__` bindings, one at a time. Canonical construction still matched the pinned module. Changing both `int_` and `_ORIGINAL_INT` to a spy caused one call to the spy with radix 16, matching the original parser's conversion route.

No native build or performance measurement was run during this audit. The source-only diagnostic exercises fallback and guard behavior, not the native scan result. The prior native result and its measured lack of whole-task speed improvement remain in `uuid-canonical-20260925.md`.

## Remaining parity limits

The scanner still bypasses observable `str.replace`, `str.strip`, and `int_` calls for accepted canonical text. Importing the private extension on its first use can be observed by an import hook that was already installed when `uuid` loaded. The added original-binding and cache names are visible through module enumeration. Like other module-level snapshots, the guard can be defeated by deliberately mutating both a live binding and its snapshot. These limits keep the scanner an opt-in experiment rather than complete UUID constructor parity.
