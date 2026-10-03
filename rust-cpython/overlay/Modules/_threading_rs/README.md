# Threading context activation

`threading` defers its private `_contextvars` import until the binding is
read. Locks, conditions, barriers, and creation of the main-thread handle do
not need it. Every `Thread.start()` resolves the binding before registering
the pending thread, including starts with an explicitly supplied context.
Default `Thread.start()` selects an empty context or a copy of
the caller's context using the existing interpreter flag. An explicitly
supplied context remains the selected context.

This changes import timing. The private `_contextvars` binding uses the
interpreter's lazy-import namespace behavior instead of eagerly storing a
concrete module. A provider replaced in `sys.modules` before first resolution
is observed at resolution rather than snapshotted at `threading` import.
An import error or interruption now occurs at first resolution, possibly
during `Thread.start()`, rather than during `threading` import. Import hooks
run before pending registration, so a successful hook that resets thread
bookkeeping cannot erase the thread's new registration. Import failure or
interruption leaves the unstarted thread unregistered and permits retry.
Failure while
selecting a context removes the pending thread registration, propagates the
same exception, and permits retry of the same unstarted thread. Registration
still precedes context selection, and native-start exception handling is
unchanged. Rollback tolerates an entry already removed by reentrant import
code or fork reinitialization.

The fresh-process fixture `rust-cpython/tests/test_threading_deferred_context.py`
covers cold synchronization and actual Rust barrier dispatch before importing
the test framework, import failure
and interruption with retry, reentrant import reset, default context
selection, and explicit context retention. It requires a target interpreter
supporting lazy imports. The separate
`rust-cpython/tests/test_threading_successful_resolution.py` checks a successful
import hook that resets pending registrations followed by a native launch
failure, including the original exception identity and native callback arguments.
`_contextvars` is a builtin module: the footprint hypothesis concerns deferred
module initialization and retained Python objects, rather than avoiding a
separate shared library. Source
review does not establish runtime correctness or a measured memory reduction.
