# UUID dependencies

- `uuid` 1.26.1: Apache-2.0 OR MIT. Provides parsing, formatting, name hashes,
  and UUID variant/version construction.
- `getrandom` 0.4.3: Apache-2.0 OR MIT. Provides operating-system entropy for
  random UUIDs; this was already the pinned transitive UUID entropy backend.

Exact versions and checksums are recorded in the overlay `Cargo.lock`.
