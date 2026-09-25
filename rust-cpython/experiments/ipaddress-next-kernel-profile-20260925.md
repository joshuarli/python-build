# IPv4 routing follow-up profile

**Decision: defer a second narrow IPv4 Rust kernel.** On the built
`--ipv4-scan` stage, the complete mixed-routing task produced the expected
digest, but integer formatting accounted for at most 4.0% of instrumented
time. The larger network operations use public, replaceable properties and
comparison behavior; this profile does not identify an isolated replacement
with enough headroom. This was one diagnostic profile, not a speed comparison.

The [raw cProfile data](data/ipaddress-next-kernel-20260925.prof) is 64,474
bytes, SHA-256
`7e2da3b7291e6104d23c9209dbf576dda6fafa4c9d9b7c82084b5575e29e8ee3`.
The checked-in [`ipaddress_v4_workload.py`](ipaddress_v4_workload.py) was
SHA-256
`995df51b4fd4ed6cf34d02517f28c7660941f804c5ba1af047561b2a00cd2a48`.
The guarded-stage interpreter and installed `ipaddress.py` hashes recorded
with its earlier build were
`f198a143f51d9a3139cb13a4b899a9dde3edc0866f9a0c1e9bfbfc11d314a306`
and
`32c8c8b0164d57430806c19b3cd5b30342e93c6aec693c6d040011988e378371`.
Those two identities were inherited from the earlier measurement record;
the stage was removed before a fresh hash check.

The successful command ran from an isolated worktree with the guarded stage
as `GUARD_PYTHON`. Its no-write cache prefix was a fresh empty directory.

```sh
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin PYTHONHASHSEED=1 \
  PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPYCACHEPREFIX="$PWD/rust-cpython/work/ipaddress-next-kernel/empty-pycache" \
  /usr/bin/time -l -p "$GUARD_PYTHON" -B -m cProfile \
  -o rust-cpython/work/ipaddress-next-kernel/profile/mixed-routing.prof \
  rust-cpython/experiments/ipaddress_v4_workload.py --count 30000 --rounds 2
```

The task reported `contained=53392`, `subnets=60000`, and output SHA-256
`71b21698342ecd72171e968712cf7218d0272ea3cbc856e94797a428a0218180`.
The profile contained 8,321,614 calls, 8,201,293 primitive, and 2.281882041
seconds instrumented total. `ipaddress._string_from_ip_int` took 0.041407
seconds self and 0.091595 seconds cumulative across 96,000 calls; even its
entire cumulative time is 4.014% of the task. Other cumulative entries were
`_is_subnet_of` 0.532057 seconds/60,000 calls, `broadcast_address` 0.344470
seconds/120,000 calls, `supernet` 0.207620 seconds/60,000 calls, and
`functools.cached_property.__get__` 0.406441 seconds/240,000 calls. These
cumulative rows overlap and must not be added.

`/usr/bin/time -l -p` reported 2.38 seconds wall, 2.34 user and 0.01 system
CPU, 39,960,576 bytes peak RSS, 27,345,376 bytes peak footprint, and zero
process swaps. No competing experiment build or benchmark was assigned at
the time, but host load was not sampled; these resources describe the
instrumented run only. The one profile attempt succeeded and no candidate
implementation was made.
