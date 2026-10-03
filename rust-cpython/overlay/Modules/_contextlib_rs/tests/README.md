# Deferred contextlib helper activation

The Python wrapper uses the existing interpreter lazy-import mechanism for `_contextlib_rs`. Importing contextlib and using suppress, closing, contextmanager or asynccontextmanager does not create the helper module and its three native method objects. Shared native image placement and every stack dispatch call stay unchanged. First stack registration or a nonempty stack unwind resolves the helper through the normal importer. Empty stacks need no backend.

The private binding remains writable before and after activation. Existing held stacks look up that same module-global binding, including after wrapper reload. No extra function cache, failure sentinel, lock, Python fallback or C bypass is added. Helper failure moves from importing public contextlib to the first operation that needs the native backend; it remains an ImportError, and a later operation can retry. This is an explicit activation boundary, not a claim of identical helper-import timing.

Eight regression cases cover a cold helper after non-stack APIs, native first dispatch and all three native callables, override/reload with held stacks, import failure and retry, reentrant publication, bounded two-thread first use, sync/async LIFO and suppression/error chains, and native use in a fresh own-GIL interpreter. Fresh source namespaces isolate wrapper state and helper entries are restored after each case. Native function provenance and forwarding are observed rather than replacing dispatch with Python emulation.

These are source-only fixtures until separately bound to a fresh build and executed under the existing owned correctness runner. The baseline must fail the cold-helper case. No memory savings, native execution or qualification is claimed by the source patch.
