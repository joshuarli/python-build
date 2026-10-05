# Compiler arena lifetime native regression

`arena_lifetime_oracle.c` is a full-ABI C embedder. It accepts exactly a matched
installed Python home and a fresh caller-owned temporary script filename. Build
it with that installation's public headers/shared libpython and the locked C
compiler; run it through the ordinary owned-process TEST controller. It creates
its script with exclusive access, closes each stream, and unlinks the file after
each case. Its expected interactive registration error is printed by CPython's
public interactive API; stderr is therefore not expected to be empty.

The observer wraps the existing MEM allocator after initialization and delegates
every operation unchanged. C-only fixed-table bookkeeping records successful
8224-byte allocations during eight controlled cases. On the 64-bit pinned
implementation this is an 8192-byte compiler chunk plus its 32-byte header.
Tracking is not a general allocation-site tracer; a different same-size owner in
these controlled cases would need investigation. The fixture uses one GIL-held
thread, creates no threads, and restores the allocator before finalization.
Allocator callbacks perform no Python operations or dynamic bookkeeping.

At each controlled exec audit event and interactive linecache registration,
allocation count must be positive and live tracked chunks must be zero. At API
return, all recorded chunks must be freed. The table is bounded and overflow
fails the judge. Realloc failure retains the original pointer record; successful
realloc updates it to the new pointer/size. All zero-size behavior remains the
underlying allocator's responsibility.

The eight cases cover file and string success, interactive success, parser
failure, runtime failure, C audit refusal, interactive registration SyntaxError
and recovery. Normal cases verify the resulting globals and code filename.
The interactive error holds its exception and verifies the caller rewrites its
text from the original source, exercising that source's ownership across
compiler-arena release. The linecache wrapper delegates normal registration to
the original callback and restores it before finalization.

The unmodified interpreter should fail because compiler chunks are still live
at exec/registration. This fixture is committed before the source correction;
no compile, baseline failure, corrected result or memory saving is claimed here.
