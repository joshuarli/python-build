# C and Rust socket module image

On macOS, when both `_socket` and `_socket_rs` are effectively configured as
shared extensions, the original C `socketmodule.c` object is compiled with
its original flags, headers and dependencies plus an initializer rename to
`_PySocket_CImage_Init`. Cargo links that object only into the actual release
`_socket_rs` cdylib. The thin Rust `PyInit__socket` export forwards to the
original C initializer; `PyInit__socket_rs` keeps its original definition.

The C extension's build and installed filenames become relative aliases to
the canonical `_socket_rs` filename. Each keeps its original extension module
name/definition; neither becomes a builtin. This changes C `_socket` from a
Mach-O bundle to Cargo's dylib and deliberately changes native image identity.
It is not transparent packaging and does not establish a memory saving.
Exact original definitions captured after first-definition precedence, default
`Modules` source directory and effective Darwin shared inventory activate the
recipe. Customized definitions/manifests/sources fall through, preserving disabled,
static, standalone helper/C and non-Darwin configurations. The C object is a
prerequisite of Cargo output; missing/nonabsolute objects or non-macOS active
context fail closed. All existing compiler and linker-helper environment and
configured C linker flags remain; no post-Cargo C link or copied-artifact
repair is permitted. The release verifier remains unchanged for all58 helpers.

Both Python module definitions, slots/flags, heap types, per-interpreter state,
GC hooks and callbacks remain independent. `_socket.CAPI` retains its exact
capsule name/table/ownership and the original C socket type referenced by
`_ssl`. Original ABI metadata and native libSystem/resolver/syscall providers
remain unchanged. Rust allocator, std/TLS, buffers, errno/EINTR handling and
GIL transitions remain original; no new dependency or feature is introduced.

Direct C `_socket` and direct `_ssl` capsule imports still leave `_socket_rs`
absent from sys.modules and preserve C I/O fallback. A helper-only import still
leaves C `_socket` absent. Loading the shared native image does not execute the
other initializer. The socket facade continues its eager optional helper import;
controlled ImportError and partially initialized helper lookups preserve their
original behavior. A C-only import now maps the existing Rust std/TLS image
before helper initialization, so singleton/startup costs must be judged directly.

The original C protected relocation metadata must retain SG_READ_ONLY and
become nonwritable after ordinary imports. Both original images already use
separate CONST/DATA segments; no disabling linker policy is propagated or
introduced. Actual final linker arguments, original compiled metadata owners
and current VM protection require independent proof. Static raw payloads can
fit fewer16KiB segments but do not predict final geometry, dirty pages or RSS.

`tests/test_socket_c_image.py` exposes one named case per fresh process so the
outer controller owns launches, whole-case deadlines, output preservation and
process/session cleanup. Baseline-normalized cases cover direct C/helper/SSL
absence boundaries, both import orders, actual unchanged fixed socket kernel
outputs/counters, restored helper dispatch after controlled import failure,
partial-helper behavior, readonly/writable/noncontiguous buffers, controlled
EINTR retry sentinels, C timeout fallback, socket subtypes/closed descriptors,
held original capsule/type/method and SSL type owners across module generations,
concurrent calls, bounded fork/reimport and three own-GIL lifetimes. Slots are
decoded by `rust-cpython/tests/socket_image_module_fixture.c`, compiled against
the actual pinned Python and socket headers. Module slots are enum/presence/stable
ABI metadata, never raw ASLR pointers. The typed CAPI observer returns owned Python
references to the original type/error fields without substituting capsule storage.
The generation test exercises the real original/candidate makesetup and dry-run
Make recipes; cleanup mocks extract the actual fork function and use only fake
descriptors and a positive owned PID. Neither compiles or loads an extension.

The deliberate merged image identity assertion must fail the original separate
packaging. Baseline semantic results must first pass unchanged. Root must later
prove actual native provider/initializer/definition/CAPI ownership and one mapped
image header in both import orders, emitted C read-only owners/current protection,
actual Cargo/member hashes, generated/evaluated Make/sysconfig inventories, and
two immutable-artifact scratch DESTDIR sharedinstall replays. Alias/inode/hash
checks alone do not prove loaded-image identity. Changed build contexts may
alter artifact bytes/metadata even with unchanged algorithms; exact release and
installed fingerprints are mandatory, including unrelated helpers.

Complete socket7, SSL19 and asyncio8 suite unions plus affected import/importlib,
interpreter, ctypes, buffer, signal and multiprocessing neighbors precede full
default-resource qualification. The unchanged all-module/all-workload memory
judge must improve socket in both runs with every guard intact. Source/fixture
review alone establishes neither correctness nor acceptance.
