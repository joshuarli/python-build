Upstream source: locked CPython 3.14.6, SHA-256 in `sources.lock.json`.
Origin: local Fil-C 3.14.6 qualification in `Lib/test/test_external_inspection.py`.
License: CPython PSF License Version 2.

Explanation: `--without-remote-debug` makes `sys.is_remote_debug_enabled()`
false, but CPython still builds the `_remote_debugging` helper extension.
The external inspection test only checks importability and then attempts
nine remote unwinds that require a PyRuntime ELF section. Pizfix's bundled
loader cannot provide that section. Skip this feature-specific test when
the runtime reports the feature disabled, matching the configured contract.

Scope: Fil-C CPython patch only.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` after the
prior Fil-C CPython patches to verified 3.14.6 source.

Regression test: `test_external_inspection` reports a capability skip;
`sys.is_remote_debug_enabled()` remains false in focused validation.
