# Token generation and compatibility grammar

`Lib/tokenize.py` sends supported simple ASCII source lines to
`_tokenize_rs.scan_line`. Unsupported source replays through CPython's tokenizer.
The Rust route, token results, source providers, encoding detection, and exception
translation keep their existing behavior.

The regular-expression grammar attributes describe the former Python scanner.
Modern token generation does not read those expressions or their quoted-prefix
containers. `Lib/_tokenize_patterns.py` constructs them on the first compatibility
attribute access. The tokenizer captures operator keys at import time, and the
factory uses independent builders. Replacing tokenizer builder functions or
mutating operator mappings later does not alter the captured grammar.

Attribute access, `from tokenize import ...`, and `dir(tokenize)` expose the
compatibility names. Before resolution, `vars(tokenize)` omits their values;
deleting such an unresolved name raises `AttributeError`. This is an intentional
private-state change. First resolution preserves already assigned overrides.
Deletion after materialization does not recreate the deleted value. Reload resets
the initializer-owned grammar names and creates fresh mutable dictionaries and
sets for that module execution. A lock ensures concurrent first readers share one
initialized graph. A single child-fork callback resets the current lock without
materializing grammar; reload replaces the lock without accumulating callbacks.

Encoding cookie and blank-line patterns still compile eagerly in `tokenize`.
Its replaceable regex and codec providers retain their existing bindings and call
behavior. The `_compile` function and its LRU cache hooks remain in `tokenize`.

`tests/test_deferred_patterns.py` covers grammar activation, successful original
Rust classifications, Unicode fallback parity, encoding/provider behavior,
import-time captures, explicit private-state behavior, mutable ownership, and
reload reset. Runtime correctness and memory qualification remain pending for this
source candidate. `tests/test_deferred_patterns_fork.py` additionally covers a
child accessing grammar while a vanished parent thread owned initialization. Its
process creation requires a separately authorized process-capable test runner;
the ordinary deferred-pattern fixture remains fork-free.
