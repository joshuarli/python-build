# Original C module core placement

The selected original C modules are `_struct`, `_heapq`, `_math_integer`, `math`,
`fcntl`, `select`, `_json`, `_queue`, `_random`, `_statistics` and `array`.
Each existing configured source row is surrounded by its own enable marker's
static directive and restoration of `MODULE_BUILDTYPE`. Missing/disabled modules
remain absent, configured shared/static ownership of following modules remains
unchanged, and earlier local registrations keep first priority. Original sources,
configured compiler/link flags and initializers are unchanged. The selected
accepted images link only the existing platform libSystem.

All Rust helpers, carrier registration, Cargo features/locks, allocation domains,
public facades, native methods and module/interpreter slots stay unchanged.
The original C objects and initializer entries move into the core library;
private loader/origin/file metadata and builtin inventory change for these eleven
modules. This is a placement experiment, not a C/Rust image fusion or helper-module
elision. Dynamic Python provider selection and held-object behavior remain live.

The exact original C struct fixture is reused unchanged. Batch fixtures add
numeric/error contracts, heap/queue/seeded-random/array ownership, pipe/select
cleanup, native JSON codecs, held owners/reload and forwarding through real Rust
heapq/JSON/random neighbors. Original C own-GIL admission is exercised separately
from helpers with existing own-GIL refusal. Candidate-only placement assertions
are separate from baseline invariant tests. Complete relevant module suites and
actual core/DSO ownership checks remain required.

A saved all-image observation reports two task-private candidate pages per
selected C image, 352KiB in total. This category is not exclusive RSS or proven
reclaimable memory. Current accepted-image section inspection finds 2,048 bytes
of static CONST, 14,096 bytes of initialized DATA and one BSS byte in the batch.
Core segment rounding tails are 12,152 CONST bytes and 14,936 DATA bytes; eleven
initializer pairs would add another 176 bytes before alignment and new bindings.
These are rounding margins, not proof that new tables land on already dirty
pages. Core table order, fixups, runtime state placement, code residency and
external-call slots can offset removal of independent-image pages. A fresh build
and memory guards must judge the combined layout; no singleton extrapolation or
RSS prediction is made.
