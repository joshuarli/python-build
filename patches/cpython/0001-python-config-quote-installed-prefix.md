# python-config: quote `installed_prefix()`'s command substitutions

- **Upstream source/version**: `Misc/python-config.sh.in` in the verified
  CPython 3.14.6 source tree (`sources.lock.json` entry `cpython`,
  `Python-3.14.6.tar.xz`, sha256
  `143b1dddefaec3bd2e21e3b839b34a2b7fb9842272883c576420d605e9f30c63`).
- **Origin / license**: original to this project; not adapted from another
  project's patch. CPython itself is Python-2.0 licensed; this diff carries
  the same license as the file it modifies.
- **Explanation**: `installed_prefix()` computes the script's own install
  location so the installed `python3.14-config` keeps working after the
  distribution tree is moved. It does so with two layers of unquoted
  command substitution (`RESULT=$(dirname $(cd $(dirname "$1") && pwd -P))`
  and `echo $RESULT`). When the install path contains a space, the shell
  word-splits the substituted path before `cd`/`dirname` see it, so `cd`
  receives multiple arguments and `installed_prefix` fails outright,
  breaking `python3.14-config --cflags/--ldflags/--includes` for every
  relocated prefix containing a space.
- **Scope**: the two unquoted substitutions in `installed_prefix()`
  (`Misc/python-config.sh.in` lines 24 and 30 in 3.14.6); no other file or
  behavior is touched.
- **Applicability check**: `build/cpython.py` fails closed with `patch
  --dry-run` before extraction is trusted; if the anchor text has moved or
  changed, the patch is rejected rather than silently skipped or force-
  applied.
- **Regression test**: `tests/test_patches.py` applies the patch to a
  scratch copy of the fetched CPython source and asserts the broken
  unquoted form is gone. The end-to-end symptom (a relocated install at a
  path with a space failing `python3.14-config`) was reproduced manually
  against an unpatched build and confirmed fixed against a patched one
  (see the M1 implementation report); that full rebuild-and-relocate cycle
  is too expensive to re-run as a unit test on every change.
- **Upstream status**: not verified against later CPython releases offline
  (no network research was performed for this pin); treat as unconfirmed
  whether this is already fixed past 3.14.6.
