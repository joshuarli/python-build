# Decimal Rust dependency licenses

Exact coefficient arithmetic uses local base-10^9 limbs and CPython-owned
temporary buffers. The helper has no third-party runtime arithmetic,
standard-library, or allocator dependency. Its existing local build-helper
crate retains its license declaration.
