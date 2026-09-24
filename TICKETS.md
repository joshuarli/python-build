# Candidate enhancement tickets

Survey date: 2026-09-23. This is a shortlist of independently implementable
ideas for this repository, informed by Astral's `python-build-standalone`
(PBS) issue and PR tracker. PBS is a technical reference only: any work below
must be designed and implemented here, with no PBS build-engine code or
binaries copied into this project.

## Priority order

### P1 — Validate Linux ELF hardening in the packaged artifact

**Status:** Implemented and validated on both Linux musl targets (2026-09-24).
The build recipes remain unchanged; package-time checks enforce the final
artifact contract.

**Why:** A PBS report documented a Linux `libpython` with an executable
`PT_GNU_STACK` segment that modern glibc systems refused to load. PBS then
merged checks for non-executable stacks and compiler hardening. Our Linux
recipe already passes `-Wl,-z,noexecstack`, `-fstack-protector-strong`, and
`-D_FORTIFY_SOURCE=2`. `buildsys.elf` parses final program headers and
dynamic symbols, and `build/package.py::compute_validation` checks the
packaged bytes after stripping and distribution pruning. This protects
against ignored flags, link-time regressions, and stripping or relinking
mistakes.

**PBS evidence:** [#1072, executable-stack regression](https://github.com/astral-sh/python-build-standalone/issues/1072)
(closed); [#1070, validate non-executable stack](https://github.com/astral-sh/python-build-standalone/pull/1070)
(merged); [#1172, request stack-protection and fortify validation](https://github.com/astral-sh/python-build-standalone/issues/1172)
(closed); [#1174, validation implementation](https://github.com/astral-sh/python-build-standalone/pull/1174)
(merged).

**Applicability and implementation:** Linux musl targets only. The
post-strip validator inspects every shipped ELF's `PT_GNU_STACK` and fails
closed on missing, malformed, duplicate, or executable records. It checks the
configured stack-protector and fortify flags, plus a post-strip dynamic
`__stack_chk_fail` reference in shared `libpython`. The small launcher is
reported but is not required to contain a guard reference when its functions
do not meet clang's selection rules. Fortify evidence uses the configured
flag because musl does not require glibc `_chk` symbols. macOS is outside the
ELF check. `AGENTS.md` records this packaging-only contract change; the
frozen Linux compile recipes are unchanged.

**Acceptance evidence:** Sealed package runs pass for x86_64 and aarch64.
Each final report contains 78 ELF objects, with no stack violations; unit
fixtures reject missing, duplicate, malformed, and executable-stack records.
Both targets retain the configured hardening flags and the shared libpython
guard reference after stripping. No runtime dependency was added; validation
uses `readelf`, already present in the sealed Linux image.

**Dependencies and risks:** The Linux targets are documented as frozen, so
this is a validation-contract change that needs an explicit record and review.
Hardening indicators differ across compiler, LTO, and libc implementations;
avoid checks that only recognize glibc conventions or reject valid musl
artifacts. The no-exec-stack invariant is directly observable in ELF program
headers and should be enforced separately from less direct fortify evidence.

### P2 — Define and implement fallback CA trust for minimal images

**Status:** Proposed; requires a trust-store scope decision. Current TLS
validation uses controlled test certificates and does not establish whether
`ssl.create_default_context()` can verify ordinary public endpoints in a
minimal runtime image.

**Why:** Minimal container images often omit OS CA packages. In that case a
Python build may import `ssl` successfully but have no usable default trust
roots. A fallback can make the interpreter more useful in minimal images,
while preserving the platform trust store when it exists.

**PBS evidence:** [#1122, bundle fallback root certificates](https://github.com/astral-sh/python-build-standalone/pull/1122)
(open PR proposal; not merged). The PR proposes a bundled Mozilla-derived
fallback and an opt-out, rather than reporting a merged PBS behavior.

**Applicability and proposed change:** All targets, subject to an explicit
decision about whether trust roots belong in this product. If accepted, lock
the certificate-bundle input with version, license, digest, and provenance;
install it under a relocatable product path; and make it a fallback only
when the platform's default trust paths are unavailable or empty. Preserve
normal platform trust behavior and document an explicit opt-out if the
implementation needs one. Do not fetch or update certificates at runtime.

**Acceptance evidence:** In a minimal Linux runtime without a system CA
store, `ssl.create_default_context()` verifies a known test endpoint/cert
chain using the bundled roots; with a platform store, the documented
platform behavior is preserved; a user-provided `SSL_CERT_FILE` continues to
work; removing or disabling the fallback produces a clear, tested outcome.
Cover macOS's system trust behavior separately and verify relocation of the
bundle. Keep private test keys and endpoints confined to fixtures.

**Dependencies and risks:** Adds a maintained trust-data input and changes
the security contract: shipped roots become trusted by default on systems
that otherwise have none. Certificate update cadence, license attribution,
revocation limitations, and opt-out semantics must be decided before
implementation. This is not implied by the current TLS round-trip check.

## Survey method and disposition

On 2026-09-23, fetched the complete paginated GitHub REST issue index for
`astral-sh/python-build-standalone` with `state=all` and `per_page=100`.
The index returned 1,262 issue/PR records: 199 open and 1,063 closed. Searched
titles across the full index for build, runtime, relocation, sysconfig,
compatibility, performance, reproducibility, security, artifact, and
packaging topics; then fetched the source issue or PR records for the
shortlisted candidates above and checked local implementation, tests, and
`AGENTS.md` requirements before selecting tickets. Upstream status is
recorded as observed on the survey date; it may change later.

Other candidates were rejected as already covered, out of scope, or
insufficiently actionable here:

- PBS #585's offline-source-download request is substantially covered by
  this project's locked inputs, content-addressed cache, `fetch` command,
  and sealed offline build path.
- PBS #1112's symlink and executable-path concern overlaps this project's
  `argv[0]`/symlink startup checks and the CPython getpath patch; no distinct
  gap was established in this survey.
- PBS #152's extension include-flag problem overlaps the existing
  post-prune extension build/load and ABI3 validation.
- PBS #306's request for a runtime library search path is covered by the
  project's `$ORIGIN` ELF relocation and `@rpath` Mach-O relocation paths.
- PBS #1200 proposes checking whether advertised object files reproduce
  exported symbols. Its companion PR is closed but unmerged, and this
  product neither ships the same advertised object-file interface nor static
  libpython archives. Existing extension and C-embedding checks are more
  directly aligned with this product contract.
- PBS #1294 proposes generic CPU scheduling for macOS arm64 and remains an
  open PR with one-machine measurements. This repository explicitly pins
  `-mcpu=apple-m1`; changing that target policy needs a separate evidence-led
  scope decision, so it is not presented as a routine enhancement ticket.
- PBS #1230/#1232's Linux build-ID work is not a useful standalone ticket
  here: Linux recipes already pass `--build-id=sha1`, and this project does
  not currently publish debug symbol files or operate a debuginfod service.

The P1 ticket is implemented; P2 remains a proposal. This work follows
the repository's source-lock, validation, and target-scope contracts.
