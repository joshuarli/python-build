# Guarded Rust URL quotation: complete-task comparison

**Measurement correction (2026-09-24):** This overlay replaced `parse.py` but
left the installed checked-hash parser bytecode cache invalid while the control
used a valid cache. With bytecode writes disabled, the candidate compiled the
parser during every fresh process. The RSS rejection below describes that
unequal-cache run; it is not a valid verdict on the Rust implementation's
memory. The [cache-attribution experiment](url-quote-memory-attribution-20260924.md)
reproduced and removed the effect. A cache-matched paired run is required.

## Decision

**Reject this overlay as a keep candidate.** On the registered 1,500-batch
`catalog_url_normalize` task, the guarded Rust quotation path reduced paired
median process wall time by 19.3% and root kernel CPU per batch by 17.4%.
Both gains exceed the clean local control's 2.97% timing allowance. But
median peak RSS rose by 3,194,880 bytes (12.4%), above the comparison's
947,346-byte RSS allowance; sampled physical footprint rose by 3,096,576
bytes. The extension also adds 1,473,544 installed bytes. This is a useful
speed mechanism with a material memory cost, not a qualifying improvement
under `rust-for-cpython.md`'s resource contract. An implementation with a
smaller resident footprint would need a new isolated comparison.

## Matched inputs and execution

I APFS-cloned the same pinned Rust fork CPython 3.16 stage twice with `cp -cR`
into this worktree's ignored `rust-cpython/work/url-quote-comparison-20260924/`.
The control clone is unmodified. In the candidate clone I replaced only
`lib/python3.16/urllib/parse.py` and added
`lib/python3.16/lib-dynload/_rust_url_quote.cpython-316-darwin.so` from the
read-only proof overlay. The source, control, and candidate executables all
have SHA-256 `6eeeb64b9eb161d4d5edb9200e79146dabd8acc0f73fcdca48417d0e3c9531bd`.
The source and control parse files retain SHA-256
`178fce6bb504b9e544ac22015778554234c63865d94374913f988bb731e0d825`;
the candidate and proof parse files have SHA-256
`8e29cff7399e7bae9e243bcc022afa43d73ad85912b9468b1e3cc73875079576`.
The candidate and proof extension files have SHA-256
`be56ff7706b06a4bb2b9eee73a47d33a4785ee0a86e071d9158ba99ccd66b371`.
I rechecked both original stage hashes after the run; they were unchanged.
The executable hash identifies `rust-cpython/stage/bin/python3.16`, which
includes the existing `_base64` integration proof. An earlier version of this
report called it the no-Rust stage. Both comparison sides used the same
executable, so the URL overlay delta remains internally matched.

Each cloned executable resolved its own `sys.prefix` and `urllib.parse.__file__`.
The candidate imported `_rust_url_quote` from its own `lib-dynload` and
returned `a%20b` for `quote('a b', safe='')`. Both clones report CPython
3.16.0a0, `cpython-316-darwin`, GIL-enabled release configuration, clang
23.1.2, `-O3`, ThinLTO, and the same nine-worker PGO task. The earlier
[`url-quote-proof-20260924.md`](url-quote-proof-20260924.md) supplies 2,177
differential cases and the unchanged `test_urlparse`/`test_urllib` pass; this
lane ran no new correctness suite.

Every timing and memory round returned 1,500 operations, input digest
`7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f`,
and complete output digest
`a6fedf33e0fd5e72b79af8d77499b9a7bb8e8d53491955f2e554570679e04941`.
Each operation performs 48 URL normalizations and 48 stable keys. The
benchmark used the standard local profile: five serial, counterbalanced
timing pairs and three separate memory pairs. Commands and full harness
outputs are under the ignored `rust-cpython/results/url-quote-comparison-20260924/`;
compact per-process observations are in
[`data/url-quote-comparison-20260924.json`](data/url-quote-comparison-20260924.json).

## Noise and results

An initial control self-comparison overlapped an unrelated `rustc` process
(PID 16513, observed at about 33% CPU) and is diagnostic only. A second
post-compiler self-comparison had 8.86% timing noise amid one-minute host
load 6.84 and other background activity. I waited for the unrelated cargo
test to finish and load to fall. The final control self-comparison started
at load 3.07 with no compiler or benchmark process observed; its paired
median wall ratio was 0.99488 and its timing allowance was 2.97%, below the
lane's 3% gate. Its RSS self-noise allowance was 400,800 bytes. The matched
comparison started at load 3.18 and had no competing compiler or benchmark
process observed. The five candidate/control wall ratios were 0.77789,
0.80988, 0.80726, 0.79922, and 0.83218; the comparison's own timing
allowance was 3.82%.

| Complete batch metric | Control median | Candidate median | Change |
| --- | ---: | ---: | ---: |
| External process wall, timing pass | 0.70991 s per 1,500 | 0.59057 s per 1,500 | paired median −19.3% |
| Internal loop wall, timing pass | 0.64981 s per 1,500 | 0.52069 s per 1,500 | −19.9% |
| Root user + system CPU, timing pass | 0.46277 ms/batch | 0.38243 ms/batch | −17.4% |
| Peak RSS, memory pass | 25,673,728 B | 28,868,608 B | +3,194,880 B (+12.4%) |
| Sampled peak physical footprint, memory pass | 12,698,080 B | 15,794,656 B | +3,096,576 B |

`/usr/bin/time -l` measured the four benchmark controller commands at
56.10 user + system CPU seconds combined, with a maximum reported RSS of
47,005,696 bytes and zero swaps. The matched controller alone took 13.10 s
elapsed, 11.81 user + 0.98 system CPU seconds, and 44,662,784 bytes maximum
RSS with zero swaps. Controller `time -l` CPU includes waited workload
children; its maximum RSS is a per-process maximum. The harness's `wait4`
CPU values cover the workload root, including startup and imports. All
memory rounds observed one workload process, so no workload descendant CPU
is missing in those rounds. Internal wall excludes startup and imports;
external wall includes them. Sampled physical footprint can miss transient
peaks. macOS unique/private or proportional memory and a compatible
allocation pass were unavailable here; steady/retained memory had no marked
boundary. The RSS increase alone exceeds the measured noise and is the
reason for rejection.
