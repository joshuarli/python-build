The helper uses the 64-bit GIL-enabled CPython object ABI through local C
signatures. `PyObject`, buffer views, method/getset tables, type specifications
and module definitions keep their original layouts and slot values. The HASH
object remains one Python object header followed by one state pointer; the
heap-type reference is released after state destruction and object storage.

The same pinned RustCrypto versions, zeroizing destructors and automatic CPU
backends remain enabled. The crates already disable their alloc defaults.
Borrowed Unicode names are consumed before buffer callbacks. Digest finalization
uses a 64-byte stack buffer and hex formatting a 128-byte stack buffer; Python
copies the returned bytes/string into its own objects. State storage uses
`malloc`/`free`, the existing default System allocation domain. The alignment
assertion bounds the crypto enum by the supported allocator's sixteen-byte
alignment. Destruction runs `drop_in_place` before freeing storage, preserving
zeroization. State allocation exhaustion still aborts as infallible Box
allocation did; the helper introduces no global allocator.

This is an unbuilt source candidate. No image-size, TLS, memory or correctness
claim follows from the source reduction. Qualification requires independent
review of the local declarations against the locked headers and an actual typed
ABI check, clean release verification of all 58 helpers, the full hashlib/hmac/
uuid suites, the ordinary Python output/type/error fixture, the existing
thread/lifetime and admitted interpreter contracts, and a coordinator-run memory
verdict. Historical same-route no_std replay closure and the actual incumbent
image/TLS map remain prerequisites before qualification. No runtime execution is
authorized by this document.
