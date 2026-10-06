The GIL-enabled type lookup cache keys exact short Unicode names by their
existing string hash and compares equal character content after matching the
captured type version. This keeps one slot for a stable type-version/spelling,
while callers still pass their original name objects to attribute hooks. It
adds no interning, module dictionary or cache-entry field. The original4096
entry capacity, owned name references, borrowed values, cache clearing and type
version invalidation remain unchanged. Historical-version entries may remain
until eviction or clearing, as before.

Exact Unicode hashing and equality cannot call Python or allocate. Non-exact
and long names retain pointer indexing and original non-cacheable behavior.
The free-threaded branch keeps its original pointer keys and synchronization.
A first miss chooses its insertion slot using the version captured with its
lookup result, including after possible MRO/dictionary reentry; it does not
reread a potentially changed current version.

The observable fixture covers fresh caller identity, descriptor dispatch,
class/negative-cache invalidation, callback errors/reentry, UTF-8 and subclass
hash errors, high-cardinality values and existing cache clearing. It passes on
the accepted runtime. Candidate compilation and ownership/memory evidence are
still required; fewer retained names do not establish a resident-page win.
