Upstream source: locked CPython 3.14.6, SHA-256 in `sources.lock.json`.
Origin: local Fil-C 3.14.6 qualification in `Modules/_elementtree.c`.
License: CPython PSF License Version 2.

Explanation: ElementTree stores a join flag in the low bit of its text and
tail pointers. Integer masking discards Fil-C capability metadata, so
copying and clearing an element traps. Use Fil-C's capability-preserving
`zandptr` and `zorptr` for this tagged pointer on the Fil-C target.

Scope: `x86_64-filc-linux-musl` only.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` to verified
CPython 3.14.6 source before configure.

Regression test: `test_xml_etree_c:test_deepcopy_clear` and the complete
`test_xml_etree_c` module run on the installed Fil-C interpreter.
