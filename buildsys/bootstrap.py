"""Toolchain and trust roots for the macOS target (plan Section 4).

LLVM is fetched from the official release archive, whose bytes, license, and
Sigstore provenance metadata are pinned in `bootstrap.lock.json`. A bounded
allowlist extracts only the compiler/runtime closure into `.cache`. Homebrew
supplies make and pkgconf; Xcode supplies the SDK and Apple linker. This
module checks the resulting tools against the lock and fails closed when a
toolchain is missing or differs.

Three things are deliberately *not* pinned here:

- **The linker.** clang's driver selects Apple's `ld` and passes the
  matching `libLTO.dylib` from its LLVM prefix, which makes ThinLTO
  work at all: a separately installed LLVM 23 compiler paired with an LLD
  from a different LLVM generation gets a bitcode-version rejection at link
  time, not a graceful fallback. The linker is recorded as an observation
  (see `linker_identity`) rather than named in the environment.
- **pkgconf's digest.** The installed revision predates the current stable
  bottle, so there is no published digest for the bytes actually present.
  It is recorded by version and path, with the gap stated, rather than
  claiming a pin that was not verified.
- **Anything in Homebrew's prefix that could be linked into the payload.**
  HOME is scrubbed and `PKG_CONFIG_LIBDIR` is narrowed so the private
  dependency prefix is the only search root; no Homebrew library may appear
  in the shipped Mach-O load commands (plan Section 1.5).
"""

from __future__ import annotations

import json
import platform
import plistlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .inputs import Input
from .recipes import Toolchain


class BootstrapError(Exception):
    """The toolchain lock is malformed or names a missing component."""


@dataclass(frozen=True)
class MacOSToolchain:
    llvm_prefix: Path
    llvm_resource_dir: Path
    llvm_version: str
    llvm_archive_url: str
    llvm_archive_sha256: str
    llvm_archive_size: int
    llvm_license: str
    llvm_release_tag: str
    llvm_source_commit: str
    llvm_attestation_url: str
    llvm_attestation_sha256: str
    llvm_attestation_size: int
    llvm_workflow: str
    llvm_archive_root: str
    make: Path
    make_version: str
    pkgconf: Path
    pkgconf_version: str
    sdkroot: Path
    xcode_version: str
    deployment_target: str
    cpu_baseline: str

    @property
    def llvm_profdata(self) -> Path:
        """The profile merger paired with the locked clang installation."""
        return self.llvm_prefix / "bin" / "llvm-profdata"

    def llvm_input(self) -> Input:
        """The exact official binary archive pinned by bootstrap.lock.json."""
        return Input(
            name="llvm-macos-aarch64",
            version=self.llvm_version,
            url=self.llvm_archive_url,
            sha256=self.llvm_archive_sha256,
            size=self.llvm_archive_size,
            role="build-source",
            target="aarch64-apple-darwin",
            license=self.llvm_license,
            purpose="official LLVM compiler and profiling tools for macOS builds",
        )

    def llvm_attestation_input(self) -> Input:
        """The digest-pinned Sigstore provenance statement for the archive."""
        return Input(
            name="llvm-macos-aarch64-provenance",
            version=self.llvm_version,
            url=self.llvm_attestation_url,
            sha256=self.llvm_attestation_sha256,
            size=self.llvm_attestation_size,
            role="build-source",
            target="aarch64-apple-darwin",
            purpose="Sigstore provenance statement for the LLVM release archive",
        )

    def toolchain(self, *, jobs: int | None = None) -> Toolchain:
        """The recipe Toolchain this lock describes."""
        binary = self.llvm_prefix / "bin"
        settings: dict = {
            "cc": str(binary / "clang"),
            "cxx": str(binary / "clang++"),
            "ar": str(binary / "llvm-ar"),
            "ranlib": str(binary / "llvm-ranlib"),
            "nm": str(binary / "llvm-nm"),
            "strip": str(binary / "llvm-strip"),
            "make": str(self.make),
            "family": "macos",
            "sdkroot": str(self.sdkroot),
            "deployment_target": self.deployment_target,
            "cpu_baseline": self.cpu_baseline,
        }
        if jobs is not None:
            settings["jobs"] = jobs
        return Toolchain(**settings)

    def identity(self) -> dict:
        """The subset that determines build output, for cache/identity use."""
        profdata_version = _tool_output([str(self.llvm_profdata), "--version"])
        return {
            "family": "macos",
            "llvm_version": self.llvm_version,
            "llvm_prefix": str(self.llvm_prefix),
            "llvm_resource_dir": str(self.llvm_resource_dir),
            "llvm_archive": {
                "url": self.llvm_archive_url,
                "sha256": self.llvm_archive_sha256,
                "size": self.llvm_archive_size,
                "license": self.llvm_license,
                "release_tag": self.llvm_release_tag,
                "source_commit": self.llvm_source_commit,
                "attestation_url": self.llvm_attestation_url,
                "attestation_sha256": self.llvm_attestation_sha256,
                "attestation_size": self.llvm_attestation_size,
                "workflow": self.llvm_workflow,
            },
            "llvm_profdata": str(self.llvm_profdata),
            "llvm_profdata_version": profdata_version.splitlines()[0]
            if profdata_version else "unavailable",
            "sdk": str(self.sdkroot),
            "xcode_version": self.xcode_version,
            "deployment_target": self.deployment_target,
            "cpu_baseline": self.cpu_baseline,
            "make_version": self.make_version,
        }


def _require(document: dict, key: str, where: str):
    if key not in document:
        raise BootstrapError(f"{where}: missing {key!r}")
    return document[key]


def load_macos_toolchain(path: Path) -> MacOSToolchain:
    """Read the macOS toolchain section of the bootstrap lock."""
    try:
        document = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise BootstrapError(f"cannot read bootstrap lock {path}: {error}") from error
    section = document.get("macos_toolchain")
    if not isinstance(section, dict):
        raise BootstrapError(f"{path}: no macos_toolchain section")
    llvm = _require(section, "llvm", "macos_toolchain")
    artifact = _require(llvm, "archive", "llvm")
    provenance = _require(artifact, "provenance", "llvm.archive")
    make = _require(section, "make", "macos_toolchain")
    pkgconf = _require(section, "pkgconf", "macos_toolchain")
    sdk = _require(section, "sdk", "macos_toolchain")
    return MacOSToolchain(
        llvm_prefix=(
            Path(path).resolve().parent
            / ".cache"
            / "llvm"
            / "toolchains"
            / f"{_require(llvm, 'version', 'llvm')}-{_require(artifact, 'sha256', 'llvm.archive')}"
        ),
        llvm_resource_dir=(
            Path(path).resolve().parent
            / ".cache"
            / "llvm"
            / "toolchains"
            / f"{_require(llvm, 'version', 'llvm')}-{_require(artifact, 'sha256', 'llvm.archive')}"
            / _require(llvm, "resource_dir", "llvm")
        ),
        llvm_version=_require(llvm, "version", "llvm"),
        llvm_archive_url=_require(artifact, "url", "llvm.archive"),
        llvm_archive_sha256=_require(artifact, "sha256", "llvm.archive"),
        llvm_archive_size=_require(artifact, "size", "llvm.archive"),
        llvm_license=_require(artifact, "license", "llvm.archive"),
        llvm_release_tag=_require(provenance, "release_tag", "llvm.archive.provenance"),
        llvm_source_commit=_require(provenance, "source_commit", "llvm.archive.provenance"),
        llvm_attestation_url=_require(provenance, "attestation_url", "llvm.archive.provenance"),
        llvm_attestation_sha256=_require(
            provenance, "attestation_sha256", "llvm.archive.provenance"
        ),
        llvm_attestation_size=_require(
            provenance, "attestation_size", "llvm.archive.provenance"
        ),
        llvm_workflow=_require(provenance, "workflow", "llvm.archive.provenance"),
        llvm_archive_root=_require(artifact, "archive_root", "llvm.archive"),
        make=Path(_require(make, "path", "make")),
        make_version=_require(make, "version", "make"),
        pkgconf=Path(_require(pkgconf, "path", "pkgconf")),
        pkgconf_version=_require(pkgconf, "version", "pkgconf"),
        sdkroot=Path(_require(sdk, "path", "sdk")),
        xcode_version=_require(sdk, "xcode_version", "sdk"),
        deployment_target=_require(section, "deployment_target", "macos_toolchain"),
        cpu_baseline=_require(section, "cpu_baseline", "macos_toolchain"),
    )


def _tool_output(command: list[str]) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as error:
        return f"<failed: {error}>"
    return (result.stdout + result.stderr).strip()


def sdk_version(sdkroot: Path) -> str:
    """The SDK's own declared version, from its SDKSettings.plist."""
    try:
        with (Path(sdkroot) / "SDKSettings.plist").open("rb") as handle:
            return str(plistlib.load(handle).get("Version", "unknown"))
    except (OSError, plistlib.InvalidFileException):
        return "unknown"


def linker_identity() -> dict:
    """Observed linker identity; recorded, not pinned (see module docstring)."""
    command = ["xcrun", "-f", "ld"]
    path = _tool_output(command).splitlines()[0].strip() if _tool_output(command) else ""
    version = _tool_output(["ld", "-v"]).splitlines()
    return {
        "path": path,
        "version": version[0].strip() if version else "unknown",
    }


def problems(toolchain: MacOSToolchain, *, host_floor: str = "") -> list[str]:
    """Every way the locked toolchain disagrees with the machine present.

    Returns an empty list when the host satisfies the lock. `doctor` reports
    these verbatim; the build fails closed on a non-empty list rather than
    silently building with a different compiler than the lock names.
    """
    found: list[str] = []
    if host_floor:
        current = platform.mac_ver()[0]
        if current and _version_tuple(current) < _version_tuple(host_floor):
            found.append(
                f"host macOS {current} is below the required floor {host_floor}"
            )
    marker = toolchain.llvm_prefix / ".verified.json"
    try:
        marker_data = json.loads(marker.read_text())
    except (OSError, json.JSONDecodeError):
        marker_data = None
    if marker_data != {
        "version": toolchain.llvm_version,
        "sha256": toolchain.llvm_archive_sha256,
    }:
        found.append(
            "official LLVM archive is not provisioned at "
            f"{toolchain.llvm_prefix}; run `python3 build.py fetch "
            "--target aarch64-apple-darwin`"
        )
    clang = toolchain.llvm_prefix / "bin" / "clang"
    if not clang.is_file():
        found.append(f"clang not found at {clang}")
    else:
        reported = _tool_output([str(clang), "--version"])
        if toolchain.llvm_version not in reported:
            found.append(
                f"{clang} reports {reported.splitlines()[0] if reported else 'nothing'}; "
                f"lock pins {toolchain.llvm_version}"
            )
        resource_dir = _tool_output([str(clang), "-print-resource-dir"])
        if Path(resource_dir) != toolchain.llvm_resource_dir:
            found.append(
                f"{clang} resource directory is {resource_dir!r}; expected "
                f"{toolchain.llvm_resource_dir}"
            )
    profdata = toolchain.llvm_profdata
    if not profdata.is_file():
        found.append(f"llvm-profdata not found at {profdata}")
    else:
        reported = _tool_output([str(profdata), "--version"])
        if toolchain.llvm_version not in reported:
            found.append(
                f"{profdata} reports {reported.splitlines()[0] if reported else 'nothing'}; "
                f"lock pins {toolchain.llvm_version}"
            )
    if not toolchain.make.is_file():
        found.append(f"make not found at {toolchain.make}")
    else:
        reported = _tool_output([str(toolchain.make), "--version"])
        if toolchain.make_version not in reported:
            found.append(
                f"{toolchain.make} does not report {toolchain.make_version}"
            )
    if not toolchain.sdkroot.is_dir():
        found.append(f"SDK not found at {toolchain.sdkroot}")
    else:
        declared = sdk_version(toolchain.sdkroot)
        if declared != "unknown" and _version_tuple(declared) < _version_tuple(
            toolchain.deployment_target
        ):
            found.append(
                f"SDK {declared} predates the deployment floor "
                f"{toolchain.deployment_target}"
            )
    return found


def _version_tuple(text: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in text.split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


_LTO_LIBRARY_C = "int answer(void) { return 42; }\n"
_LTO_MAIN_C = (
    "#include <stdio.h>\n"
    "extern int answer(void);\n"
    "int main(void) { printf(\"%d\\n\", answer()); return answer() != 42; }\n"
)


def lto_smoke_test(toolchain: Toolchain, workdir: Path) -> dict:
    """Prove the locked compiler and linker can actually build and run ThinLTO.

    This is the gate plan Section 5.1 requires before any dependency build.
    On macOS the risk is specific and silent: clang passes its own
    `libLTO.dylib` to the platform linker, so a compiler/linker generation
    mismatch surfaces as a hard bitcode rejection — but only if LTO is
    actually exercised. A build that quietly dropped `-flto` would otherwise
    look like a pass, so the deployment floor and architecture of the result
    are inspected too, not just the exit status.
    """
    from . import macho

    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    library = workdir / "lto-library.c"
    main = workdir / "lto-main.c"
    library.write_text(_LTO_LIBRARY_C)
    main.write_text(_LTO_MAIN_C)
    objects = workdir / "lto-library.o"
    archive = workdir / "liblto.a"
    binary = workdir / "lto-smoke"
    base = [toolchain.cc, "-O3", toolchain.cpu_baseline,
            f"-mmacosx-version-min={toolchain.deployment_target}", "-flto=thin"]

    steps = [
        (base + ["-c", str(library), "-o", str(objects)], "compile library"),
        ([toolchain.ar, "cr", str(archive), str(objects)], "archive"),
        (base + [str(main), str(archive), "-o", str(binary)], "link with thinlto"),
    ]
    for command, description in steps:
        result = subprocess.run(
            command, capture_output=True, text=True, env=toolchain.env()
        )
        if result.returncode != 0:
            raise BootstrapError(
                f"LTO smoke test failed to {description}: "
                f"{(result.stderr or result.stdout).strip()[:400]}"
            )

    # Prove -flto actually took effect. If the flag were dropped or ignored,
    # the object would be an ordinary Mach-O and the build would report a
    # passing LTO gate while shipping non-LTO code. Darwin emits bitcode
    # inside a wrapper (0x0B17C0DE) rather than the bare 'BC\xc0\xde' form,
    # so both count as bitcode and anything else is a failure.
    magic = objects.read_bytes()[:4]
    if magic not in (b"BC\xc0\xde", b"\xde\xc0\x17\x0b"):
        raise BootstrapError(
            f"LTO smoke object is not LLVM bitcode (magic {magic!r}); "
            f"-flto=thin was not honoured by {toolchain.cc}"
        )

    run = subprocess.run(
        [str(binary)], capture_output=True, text=True, env=toolchain.env()
    )
    if run.returncode != 0 or run.stdout.strip() != "42":
        raise BootstrapError(
            f"LTO smoke binary did not run correctly: rc={run.returncode} "
            f"out={run.stdout.strip()!r} err={run.stderr.strip()!r}"
        )

    header = macho.read_header(binary)
    version = macho.build_version(binary)
    report = {
        "compiler": toolchain.cc,
        "lto_mode": "thin",
        "arch": header.arch,
        "minos": version.minos if version else None,
        "sdk": version.sdk if version else None,
        "expected_minos": toolchain.deployment_target,
        "runs": True,
    }
    if report["arch"] != "arm64":
        raise BootstrapError(f"LTO smoke produced {report['arch']}, expected arm64")
    if report["minos"] != toolchain.deployment_target:
        raise BootstrapError(
            f"LTO smoke minos {report['minos']} != declared floor "
            f"{toolchain.deployment_target}"
        )
    return report


def toolchain_for(target, lock_path: Path, *, jobs: int | None = None) -> Toolchain:
    """The toolchain a target's recipes build with.

    The macOS toolchain is resolved from the bootstrap lock and verified
    against the machine before any compilation starts, so a toolchain that
    silently changed under the lock fails here rather than producing an
    artifact nobody can attribute. The Linux targets keep the bare-name
    toolchain their container's PATH provides.
    """
    if not target.is_macos:
        return Toolchain(jobs=jobs) if jobs else Toolchain()
    locked = load_macos_toolchain(lock_path)
    found = problems(locked, host_floor=locked.deployment_target)
    if found:
        raise BootstrapError(
            "locked macOS toolchain does not match this machine: " + "; ".join(found)
        )
    return locked.toolchain(jobs=jobs)
