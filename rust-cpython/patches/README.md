# Source patches for the Rust candidate

`build.py build` extracts the archive pinned in `sources.lock.json`, verifies
its `Cargo.lock`, then applies the ordered patches in `manifest.json` before
checking Cargo dependencies or compiling. `build_no_rust.py` extracts the same
archive without these candidate patches, keeping its control identity explicit.

For each patch, add a unified Git diff named `*.patch` and an entry with
`file`, lowercase SHA-256 `sha256`, `author`, `origin`, `license`, `reason`,
`compatibility`, and `reproducer`. `author` names the person or organization responsible for
the edit; `origin` identifies where it came from. `reason` explains the
experiment; `compatibility` names the pinned source assumptions and behavior
checks that justify applying it. Keep these fields precise enough for a later
reviewer to assess authorship and compatibility without generated `work/`
contents. `reproducer` identifies the focused test or command that demonstrates
the need for the patch. The manifest's `source_commit` must match
`sources.lock.json`.

The builder checks all patch digests before changing the source tree. Git
applies each patch with context checks and rejects unsafe paths. It checks
`Cargo.lock` again after application. A failure stops the build; the next
build starts from a fresh verified extraction. The build report records the
manifest digest and every patch entry. Do not patch `Cargo.lock`, add Cargo
dependencies, or use the patch lane to change the production 3.14.6 build.
