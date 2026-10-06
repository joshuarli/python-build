# Difflib matching helper

The helper compares built-in immutable values through the existing position
index. Its matching algorithm, earliest-position tie rule, input snapshots,
public output and Python fallback remain unchanged.

The private `snapshot_matches(list, snapshot, tuple_factory)` entry returns
`1` for equal exact lists/tuples of exact strings or integers, `0` for unequal
eligible inputs, and `-1` when the original tuple comparison is required. It
validates both containers completely before comparison and declines for a
replaced tuple constructor. Invalid argument count raises `TypeError`.

The facade remembers its original native module with a builtin weak reference,
so eviction and backend replacement do not extend that module's lifetime.
The method is looked up live. An initial custom backend, including an exact
module with only the original matching interface, remains on the legacy path.
Native identity requires its own builtin matching method bound to that module,
read directly from the module dictionary. The temporary initializer and method
reference are discarded; custom attribute getters are not consulted. A replaced backend keeps the earlier matching-only interface; it does
not need to implement this new entry. Deleting the entry from the actual
native module is an error rather than an implicit provider fallback.

The experiment removes only the temporary `tuple(self.b)` used to check the
historical snapshot. The reordered workload has 396 entries: about 3,208 bytes
of tuple storage, including the header. The historical `b` snapshot, `a`
snapshot and matching scratch remain. A native function, a weak-reference object and lightweight constructor/type
bindings are added; no physical-memory saving or cause of a workload regression
is established by this logical budget.

`tests/test_snapshot_comparison.py` covers mutation, equal strings with distinct
identities, custom equality and exceptions, reentry, live tuple/backend hooks,
range errors, earliest ties, the complete fixed patch digest and native
routing. Its separate optimization case requires the new private entry.
