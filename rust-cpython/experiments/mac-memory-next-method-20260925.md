# macOS page-info memory scout (2026-09-25)

## Decision

No qualifying exact or useful bounded USS/PSS route is established through the
installed public Mach interfaces. Keep both fields unavailable for CPython 3.16
parity. The next *diagnostic* method is a sparse `mach_vm_region_recurse` plus
`mach_vm_page_info(VM_PAGE_INFO_BASIC)` checkpoint scan. It can test whether
Mach resolves the submap failure of `PROC_PIDREGIONINFO`; it must not publish
USS/PSS merely because its per-page records can be summed.

`mac-region-probe-20260924.md` found 18 submaps per walk and raw resident pages
far above libproc RSS. The existing RSS and `phys_footprint` fields remain
different quantities, as `mac-footprint-20260924.md` explains. This scout ran
no process probe; the proposed method is unmeasured.

## Why the apparent per-page route fails

The macOS 26 SDK declares `mach_vm_region_recurse` with an in/out nesting
depth and `vm_region_submap_info_64.is_submap`; the header explains how to
re-enter a submap. It also declares `mach_vm_page_info` returning disposition,
`ref_count`, object ID, object offset, and shadow depth for one address. Those
fields look sufficient to deduplicate virtual aliases and weight shared pages.
They are not a physical-page identity or a global mapper count.

Apple's [XNU page-info implementation](https://github.com/apple-oss-distributions/xnu/blob/main/osfmk/vm/vm_map.c)
sets `ref_count` from the VM **object's** reference count and explicitly calls
it a ballpark overcount: references can exist without mapping this page or
even its section. `VM_PAGE_QUERY_PAGE_PRESENT` comes from looking up a page in
that object or its COW shadow chain; it does not prove a faulted-in mapping in
the target task's physical map. The returned object ID is a hash of the VM
object, not an exported physical frame number. The same implementation can
also synthesize ledger pages for footprint mode. Thus `(object ID, offset)`
deduplication and division by `ref_count` cannot establish USS or PSS, or a
defensible nontrivial bound on either. `mach_vm_page_query` forwards these
same semantics; the range query exposes only disposition flags.

Apple's [VM-region header](https://github.com/apple-oss-distributions/xnu/blob/main/osfmk/mach/vm_region.h)
warns that sharing modes are loosely defined and best-effort accounting.
Apple's [virtual-memory guidance](https://developer.apple.com/library/archive/documentation/Performance/Conceptual/ManagingMemory/Articles/VMPages.html)
explains that a COW region can mix shared and private pages and that submaps
can be shared machine-wide. Object `ref_count` cannot distinguish those pages
or account for all processes outside the workload tree that map them.

## Precise next probe and stops

At a held checkpoint in one ordinary same-user CPython 3.16 child, obtain a
read-capable task port under normal user permissions; stop if that fails.
Enumerate regions with `mach_vm_region_recurse`, incrementing nesting depth
and re-entering each returned submap until leaves are reached. Reject a scan
on any error other than documented end-of-map, overlapping/nonprogressing
ranges, missing leaf, or changed PID birth identity. Record each leaf once;
compare leaf region counts and resident totals with `vmmap -submap` and libproc
RSS, without treating agreement as proof of USS/PSS. Query `mach_vm_page_info`
for a small, known set of touched pages: private anonymous, two aliases of
one shared mapping, parent/child COW before writing, and the child's pages
after writing. Capture disposition, object ID/offset, shadow depth, and
`ref_count`; verify that alias and COW transitions expose the limitations
above. Avoid scanning every page of the interpreter merely to confirm a
source-level semantic failure.

For each checkpoint, verify the process-group/descendant set and each PID's
start identity before and after collection, as the current harness does.
Any missed, exited, denied, or newly spawned member invalidates a tree
snapshot. Separate sequential per-PID reads cannot create an atomic tree
peak; short-lived children remain unmeasured. Use the probe only outside timed
workload passes. Record wall and user/system CPU time for the complete
observer and child process tree, observer peak RSS, page-query count, and time
per checkpoint; stop at 30 CPU seconds or 512 MiB observer RSS. Stop the
method entirely if a task port requires root, debugger entitlement, SIP or
signing changes, if traversal cannot cover leaves, or if the observer materially
perturbs a short workload. A successful traversal would justify only a
separately named sparse VM diagnostic, after its own semantic checks; it does
not reopen USS/PSS parity without a documented per-physical-page mapping
identity and global process mapper count.

## Scope and resources

Read-only SDK/header, local source/report, and Apple documentation/XNU source
inspection only. No builds, benchmarks, process probes, tests, dependencies,
formatters, linters, or hooks. No substantial CPU or memory command was run.
