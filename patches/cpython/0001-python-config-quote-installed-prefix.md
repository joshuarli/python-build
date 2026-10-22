# python-config: quote `installed_prefix()`'s command substitutions

- **Upstream source/version**: `Misc/python-config.sh.in` in the verified
  CPython 3.15.1 source tree (`sources.lock.json` entry `cpython`,
  `Python-3.15.1.tar.xz`, SHA-256
  `673ae7232d84c894729882c8257d300ef2d26523911bfd3917ec8ce7f526f99b`).
- **Origin / license**: original to this project; not adapted from another
  project's patch. CPython itself is Python-2.0 licensed; this diff carries
  the same license as the file it modifies.
- **Explanation**: `installed_prefix()` computes the script's own install
  location so the installed `python3.15-config` keeps working after the
  distribution tree is moved. It does so with two layers of unquoted
  command substitution (`RESULT=$(dirname $(cd $(dirname "$1") && pwd -P))`
  and `echo $RESULT`). When the install path contains a space, the shell
  word-splits the substituted path before `cd`/`dirname` see it, so `cd`
  receives multiple arguments and `installed_prefix` fails outright,
  breaking `python3.15-config --cflags/--ldflags/--includes` for every
  relocated prefix containing a space.
- **Scope**: the two unquoted substitutions in `installed_prefix()`
  (`Misc/python-config.sh.in` lines 24 and 30 in 3.15.1); no other file or
  behavior is touched.
- **Applicability check**: `build/cpython.py` fails closed with `patch
  --dry-run` before extraction is trusted; if the anchor text has moved or
  changed, the patch is rejected rather than silently skipped or force-
  applied.
- **Regression test**: `tests/test_patches.py` applies the patch to a
  scratch copy of the fetched CPython source and asserts the broken
  unquoted form is gone. The end-to-end symptom (a relocated install at a
  path with a space failing `python3.15-config`) was reproduced manually
  against an unpatched build and confirmed fixed against a patched one; the
  production relocation qualification repeats the installed command check.
- **Upstream status**: the patch applies to the verified 3.15.1 source with
  zero fuzz and its regression test confirms the unquoted form remains there.
