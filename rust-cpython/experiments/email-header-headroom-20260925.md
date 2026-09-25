# Email header native-boundary diagnostic

**Decision: defer a Rust header token scanner.** The complete pinned archive workload has measurable header work, but the expensive `headerregistry.py` cumulative path combines dynamic class creation, lazy policy fetches, structured header parsing, token-tree traversal, serialization, and application indexing. A scanner that only recognizes text spans would address a much smaller part of that path. The diagnostic identifies no narrow substitution that preserves the public `email` behavior and is likely to repay the native boundary cost.

## Reproduction and identity

Run from the experiment worktree with the pinned installed CPython 3.16 stage:

```sh
/usr/bin/time -l /Users/josh/d/python-build/rust-cpython/stage/bin/python3.16 -B rust-cpython/experiments/email-header-headroom-20260925.py --iterations 5
/usr/bin/time -l /Users/josh/d/python-build/rust-cpython/stage/bin/python3.16 -B rust-cpython/experiments/email-header-headroom-20260925.py --iterations 5 --profile
```

The diagnostic imports the unchanged `email-workload-20260925.py`, verifies its SHA-256 `9a0ab388d856435b29ab0fbdc0b73617de90ffc470e7ff4a746fc80d641a8792`, the interpreter SHA-256 `6eeeb64b9eb161d4d5edb9200e79146dabd8acc0f73fcdca48417d0e3c9531bd`, the source-lock SHA-256 `7417c031b6ef4bc1a54963bad20455173c1be40bb51927bc523448dbacdcece9`, and all 11 fixture hashes before timing. The output SHA-256 in every completed attempt is `e5faf8d7b11d84b98aef05bb543b77eecb8ae5324b13467bf0d6136b37572534`: 11 messages, 72 parts, 27,194 input bytes, and 27,140 serialized bytes per operation. It repeats exactly the workload's original parse, index, serialize, reparse, equality check, and output-digest construction. Only measurement boundaries change.

`data/email-header-headroom-20260925.json` keeps shared interpreter, source, workload, and fixture identities in `recipe.pinned_identity` once. Its seven attempt records retain the initial combined reparse/index diagnostic, its superseding five-phase runs, task and whole-process wall time, kernel-accounted user and system CPU, RSS high-water marks, zero swaps, output identity, and the per-phase profile. `/usr/bin/time -l` covers process startup and imports; task resource values use `getrusage(RUSAGE_SELF)` around five archive operations and cover no child processes. The host had load averages near 3. The timings are diagnostic, not a control/candidate speed comparison.

## Disjoint phase attribution

The final plain phase-timer attempt completed five full archive operations in 0.1493 seconds task wall time, 0.1467 seconds task user CPU, and 0.0018 seconds task system CPU; process peak RSS was 31,440,896 bytes. Whole-process values were 0.21 seconds wall, 0.18 user CPU, 0.01 system CPU, and 31,457,280 bytes peak RSS. These phase times are disjoint and sum to 0.1480 seconds; the small remainder is digesting, equality checks, and loop bookkeeping.

| Phase, five operations | Plain wall seconds | Share of task wall |
| --- | ---: | ---: |
| Original parse | 0.0336 | 22.5% |
| Original index | 0.0281 | 18.8% |
| Serialize | 0.0285 | 19.1% |
| Serialized reparse | 0.0323 | 21.6% |
| Serialized index | 0.0256 | 17.1% |

The serialized reparse and index exist solely to verify the workload's round-trip invariant; together they consume **38.7% of plain task wall time**. Original parse plus serialized reparse account for roughly 44% of this complete diagnostic operation. An ingest that parses and indexes each original once would omit the second parse and index, so the current workload overstates parser share for normal archive ingest. Serialization also refolds headers, so the complete operation exercises parser code beyond inbound ingestion.

## Disjoint self-time attribution

The final per-phase `cProfile` attempt took 0.4960 seconds task wall and 0.4922 seconds task user CPU, with 31,850,496 bytes process peak RSS; whole process used 0.57 seconds wall, 0.53 user CPU, 0.02 system CPU, and 32,210,944 bytes peak RSS. Its five profile totals sum to 0.4916 seconds of disjoint self time. Instrumentation triples task time relative to the plain attempt, so these seconds locate work; they do not predict a speedup.

| Source, five operations | Profile self seconds | Share of disjoint profile self time |
| --- | ---: | ---: |
| `_header_value_parser.py` | 0.2101 | 42.7% |
| Built-ins and C calls | 0.1308 | 26.6% |
| `headerregistry.py` | 0.0531 | 10.8% |
| `message.py` | 0.0310 | 6.3% |
| `feedparser.py` | 0.0224 | 4.6% |
| `policy.py` | 0.0107 | 2.2% |
| Other Python, generator, parser, and diagnostic code | 0.0336 | 6.8% |

The per-phase `_header_value_parser.py` self seconds were 0.0515 original parse, 0.0379 original index, 0.0345 serialization, 0.0487 reparse, and 0.0374 serialized index. Thus header parsing is repeated by application getters and serialization, not concentrated in feed parsing. The previous workload's roughly 0.35-second cumulative `HeaderRegistry.__call__` value includes its callees and overlaps `message.get`, `policy.header_fetch_parse`, and token parsing. It is not additive to these self-time figures.

Three plausible lexical helpers, `_get_ptext_to_endchars`, `get_fws`, and `get_ttext`, total only 0.0182 seconds of profiled self time (3.7% of total). That is an intentionally generous ceiling for a scanner replacing those whole functions: `get_fws` and `get_ttext` also construct Python token objects and `get_ttext` registers defects. `parse_content_type_header`, `get_parameter`, `TokenList.params`, and `TokenList.all_defects` carry substantial additional self time, but they implement structured semantics, object creation, recovery, and traversal; calling their full cost "scanning" would overstate a lexical kernel.

## Boundary constraint

The pinned `policy.py` keeps source headers raw and parses them lazily through `header_fetch_parse`; callers may supply a custom `header_factory` and `message_factory`. `HeaderRegistry.__getitem__` creates a new specialized class with `type(...)` on each fetch (4,395 calls in the earlier full-workload profile), and `BaseHeader.__new__` invokes class-specific parsing and initialization. `feedparser.py` itself fetches `Content-Type` and related headers while constructing MIME structure. A native replacement at `Message.get` or policy fetch would need to preserve dynamic classes, custom factories, defects, encoded words, malformed input behavior, and generator refolding. A pure lexical span scanner avoids most of that contract but has little measured headroom here.

A future proposal needs a specific semantic subset and an end-to-end candidate/control comparison on a quiet host using this exact output identity, with an ingest-only companion workload if the goal is ordinary archive ingestion. This lane makes no native change or timing-win claim.
