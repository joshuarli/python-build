# Optional Nix-backed Linux builder prototype

**Not NixOS, and not a new production backend.** NixOS is a full operating
system; replacing Alpine with a stock NixOS image would introduce a different
libc/toolchain and break the exact musl and compiler contracts. Here, Nix is an
alternative, declarative *supplier of the exact locked Alpine and Rust bytes*.
The existing Dockerfiles still install the packages and produce the native
Linux build environment; the existing RTLS build and qualification code remains
authoritative. No Nix store paths should enter the released Python payload.

This prototype covers `linux/amd64` and `linux/arm64`. It does not modify the
macOS/Xcode build, the release target set, or the default Docker path.

## Usage

Prerequisites: Nix with flakes enabled, Docker BuildKit, Python 3, and a native
Linux Docker daemon matching the target (`amd64` or `arm64`). Nix may run on
macOS while Docker uses a native-architecture Linux VM; contexts are built by
the host Nix, not a cross-compiled Linux Nixpkgs toolchain.

```sh
# Build only the immutable Docker contexts. Nix verifies every fetched hash.
nix build --no-link --no-update-lock-file .#base-arm64
nix build --no-link --no-update-lock-file .#rtls-arm64

# Build both native Docker images, validate the entire APK closure, and emit a
# machine-readable builder record. Use --arch amd64 on native x86-64 Linux.
python3 nix/build_image.py --arch arm64
```

The script also seeds the existing `.cache/bootstrap` package and Rust
component caches from Nix's independently hash-verified inputs. Any mismatched
existing cache bytes fail closed rather than being overwritten. It does not
replace the separate source/Cargo fetch phase.

The script prints two image references. Explicitly opt in to using them for
an otherwise unchanged RTLS fetch/build/qualification run:

```sh
PYTHON_BUILD_NIX_BASE_IMAGE='python-build-nix-arm64:base-<context-hash>' \
PYTHON_BUILD_NIX_TOOLCHAIN_IMAGE='python-build-nix-arm64:rtls-<context-hash>' \
python3.15 backend/docker-linux.py \
  --phase all \
  --target aarch64-unknown-linux-musl \
  --run-dir .work/tmp/nix-prototype-arm64 \
  --jobs 6 \
  --rtls-source .work/tmp/rtls-linux-source
```

Obtain the exact tags from the script's JSON output; the example tags are
placeholders. Follow `backend/LINUX.md` for the required
clean checkout, source fetch, and work-directory preparation. For amd64 use
`x86_64-unknown-linux-musl`, `--arch amd64`, and a native amd64 Docker daemon.

The runtime still uses the separately locked Alpine image, and the existing
archive, ABI, musl dependency, OpenSSL-free, regression, and relocation gates
still run. A successful image build **does not qualify the CPython release**.

## Reproducibility contract

- `flake.lock` pins Nixpkgs (used for host-side fixed-output downloads and
  deterministic context assembly). No Nixpkgs compiler or libc enters Docker.
- `bootstrap.lock.json` pins the exact Alpine image digests, LLVM/APK package
  closure, versions, URLs, hashes, and architectures.
- `backend/linux-bootstrap*.json` pins the supplemental APKs
  and the native-musl Rust toolchain archives.
- The two Nix derivations copy the original, unchanged `Dockerfile` and
  `Dockerfile.linux`, plus exactly those verified input bytes, into isolated
  BuildKit contexts. BuildKit `RUN` steps are network-disabled.
- `build_image.py` verifies native architecture, all installed APK versions,
  LLVM 23.1.3, the locked Rust version and host, and existing image labels.
  It records Nix/OCI identities under `.work/tmp/` by default.
- The optional override is fail-closed: both images must be named and their
  architecture, base digest, and hashed bootstrap identity must match the
  repository's locks. Without the override, production behavior is unchanged.

**Availability caveat:** Nix hashes verify content, but do not archive it.
Some pinned Alpine edge URLs have already expired. A cold Nix fetch may fail
until those exact APK bytes are preserved in a durable source/substituter. Do
not silently re-resolve package versions or point at a newer Alpine release.
Previously populated `.cache/bootstrap` files are *not* automatically Nix
store inputs. The wrapper explicitly copies Nix-verified bytes into those
caches, preserving the existing driver's independent verification boundary.

**Not yet demonstrated:** This environment has not been built/qualified on a
native host as part of this prototype. Run the full existing qualification and
independent two-build byte comparison before claiming equal output hashes,
bit-reproducibility, or a supported Nix-backed release path.
