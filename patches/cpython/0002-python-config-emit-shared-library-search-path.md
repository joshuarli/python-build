# python-config: emit the shared libpython's search path

- **Upstream source/version**: `Misc/python-config.in` in the verified
  CPython 3.14.6 source tree (`sources.lock.json` entry `cpython`,
  `Python-3.14.6.tar.xz`, sha256
  `143b1dddefaec3bd2e21e3b839b34a2b7fb9842272883c576420d605e9f30c63`).

- **Origin / license**: original to this project; not adapted from another
  project's patch. CPython itself is Python-2.0 licensed; this diff carries
  the same license as the file it modifies.

- **Explanation**: `python3.14-config --ldflags --embed` is the advertised
  contract for linking an embedder against the shipped shared libpython. The
  upstream script emits `-L<libdir>` only when there is *no* shared library,
  on the assumption that a shared libpython sits in a directory the linker
  already searches. That assumption holds for a distribution installed at a
  system prefix and fails for a relocated, self-contained tree: the linker is
  left with a bare `-lpython3.14` and no search path, so every embedder build
  fails with `ld: library 'python3.14' not found`. The fix derives the lib
  directory from the runtime standard-library path — `sysconfig` computes
  that from the running interpreter's own location — instead of the
  configure-time `LIBDIR`, which is baked to the build prefix and would send
  the linker back to a directory that does not exist on the consumer's
  machine.

- **Scope**: the `--ldflags` branch of `Misc/python-config.in` plus the
  `import os` it needs. Because CPython's Makefile installs the Python
  variant of this script only on Darwin (`python-config.sh` is used
  elsewhere, and the shell version already emits `-L`), this change is
  macOS-only in effect; it does not alter the Linux targets' output.

- **Applicability check**: `build/cpython.py` fails closed with `patch
  --dry-run` before extraction is trusted; if the anchor text has moved or
  changed, the patch is rejected rather than silently skipped or
  force-applied. The anchor is the upstream comment and the
  `Py_ENABLE_SHARED` condition, so a future CPython that fixes this upstream
  causes a clean rejection rather than a double-negation.

- **Regression test**: `tests/test_patches.py` applies the patch to a
  scratch copy of the fetched CPython source and asserts the inverted
  condition is present and that `-L` is emitted on the shared path.
  End-to-end, `buildsys/validate_macos.py`'s `embedding_checks` compiles and
  runs a C program against `python3.14-config --cflags --ldflags --embed`
  from the relocated tree; that check failed before this patch and passes
  after it.

- **Upstream status**: not verified against later CPython releases offline
  (no network research was performed for this pin); treat as unconfirmed
  whether a later version derives the search path itself.
