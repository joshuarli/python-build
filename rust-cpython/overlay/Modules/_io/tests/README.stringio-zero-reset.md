StringIO zero truncation
======================

The source retains the pinned CPython StringIO implementation except for
shrinking nonempty contents to zero. That transition prepares an empty Unicode
writer, shrinks the dormant UCS4 buffer, and publishes a valid accumulating
state before releasing the old writer. It does not change the cursor, newline
decoder, read/write newline policy, module state, or critical section.

The ordinary fixture covers held content, Unicode, cursor gaps, newline history,
pickle, argument reentry, subclasses and errors. Its six tests are prepared but
not executed. The C allocator observer is for a separate fresh GIL-enabled
process without threads or other interpreters. It temporarily wraps the MEM
domain around one exact native StringIO.truncate(0) call. Before installing
hooks, it resolves the receiver type's defining module with PyType_GetModule,
requires identity with the published _io module and its original native
module definition,
requires identity with that module's exported immutable StringIO type, and
binds its truncate descriptor to the receiver, then compares the native
callback, flags and receiver. Instance dictionaries cannot substitute a
different bound method for the expected dispatch. A replaced
module export fails closed; a Python subclass has no defining-module association
of its own. Type names alone are not admission facts; replacing the import-table
entry also fails this controlled fresh-process probe's module identity check.
Spoofed subclasses, Python overrides, another native method and an instance
attribute shadowing truncate with read are rejected
before hooks, with the probe's prior statistics unchanged. It delegates malloc,
calloc and free, and rejects only realloc sizes at or above a supplied threshold.
It restores the allocator before returning or propagating the held exception.
The original allocator also remains the provider for accepted requests.

The allocation fixture rejects a whole discarded UCS4 payload while leaving
small metadata and Python object allocation available. The original source
attempts that payload in realize() and is expected to fail this regression;
this expectation is not an executed result. A second case rejects shrinking a
realized buffer and checks that text and cursor survive MemoryError. It then
performs a successful reset and gap write. The observer reports MEM realloc
request counts only, not physical memory or a complete allocation graph.

PyUnicodeWriter_Create(0) may obtain the writer from the interpreter freelist,
or use a small PyMem_Malloc. Its empty writer has no character buffer.
PyUnicodeWriter_Discard releases its Unicode storage and returns the writer to
that freelist. StringIO's resize_buffer uses PyMem_Realloc; requests exceeding
the small-object cutoff reach the underlying raw allocator through the original
MEM provider. No allocator policy, capacity, free-list or Rust route is changed.

The logging kernel still creates ordinary handlers, writes one whole record at
a time and calls the Rust message formatter. A fixed logging kernel reuses the
StringIO and therefore exercises this transition. The source-defined avoided
materialization exists on both incumbent and the smaller-arena experiment; it
does not establish the cause of their different working peaks or any physical
savings. Builds, full I/O and logging suites, native coverage and actual memory
guards remain required before qualification.
