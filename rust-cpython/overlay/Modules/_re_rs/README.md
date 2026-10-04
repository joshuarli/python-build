# Borrowed compiled-expression searches

Public ASCII searches reuse the immutable SRE program already owned by the canonical
`re.Pattern`. Rust validates and executes that program and returns only search
status and span. Python keeps the compiled pattern alive during the call; C still
creates the canonical Match and capture objects through the existing adapter.
The ordinary route does not prepare a second regex engine, populate the Rust
expression cache, or enter the parser scratch arena.

`re_rs_borrow_pattern` is a private typed C boundary in the helper's
`pattern_view.c`. The interpreter's `_sre` source remains unchanged. The getter
obtains the static module definition from `PyInit__sre`, which returns the
already initialized definition without importing a module or executing slots.
It checks the pinned five-pointer module-state size before reading that state,
and uses `PyType_GetModuleByDef` to recognize the exact defining module and its
Pattern type. It checks that the source is an exact ASCII Unicode object and lends
its immutable `uint32_t` code, code length, source and resolved flags. No reference
is transferred. Arguments belong to the calling interpreter. The Pattern
argument must remain live and the GIL held until
Rust finishes reading both borrowed slices. Wrong types or non-ASCII source
return unsupported; no pattern-object layout is reproduced in Rust. C uses the
configured interpreter's `Modules/_sre/sre.h`, including its conditional debug
fields, and its generated `pyconfig.h`. `build.rs` compiles and archives the
accessor with `PY_CC`, `PY_CPPFLAGS`, `PY_CFLAGS`, and the configured archiver,
without a new crate. The exported flags retain the configured target, SDK, and
deployment selection; the helper adds only PIC, hidden visibility, and the
configured build/source include directories. It does not claim to receive the
expanded core module's `PY_STDMODULE_CFLAGS` value.

`prepare_compiled(pattern)` checks the existing portable syntax selector, flags
0 or 32, and supported bytecode without building a duplicate program.
`search_compiled(pattern, subject)` returns `(0, 0, 0)` for unsupported inputs,
`(1, 0, 0)` for a definitive no-match, or `(2, start, end)` for a match. Wrong
argument counts are unsupported. Non-Unicode and non-ASCII subjects are rejected
before obtaining UTF-8. Execution allocation failures raise MemoryError; invalid
programs raise RuntimeError. Runtime continuation storage is call-local, and
covered expressions must not fall back merely because a fixed stack limit is hit.

The private string APIs `prepare(source, flags)` and
`search(source, subject, flags)` remain functional with their original engines.
`_legacy_hooks_intact()` compares both native function pointers and bound-module
identities each time. The Python adapter selects the borrowed route only when
those identities are unchanged and both compiled methods are available.
Replacing either legacy callable, or using a helper without the new methods,
keeps the original string calls. Module state, slots, ownership hooks, Cargo
inputs and coverage of unsupported public expressions retain their existing
behavior. This implementation does not establish a physical memory saving.
