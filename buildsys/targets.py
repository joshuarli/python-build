"""Target description: the one place architecture-specific data lives.

Plan Section 12: "Every recipe, the CPython configure policy, and validation
share one dependency graph, one Toolchain, and one packaging pipeline; only
the handful of values below differ by machine." The running interpreter's
own `platform.machine()` is what's actually true inside a given container or
on a given host (including a QEMU-emulated one, which reports the emulated
architecture, not the host's) — target selection reads that rather than
trusting an external flag that could disagree with reality.

Two families are implemented, and they are deliberately different shapes:

  linux-musl  Alpine userspace in a Dockerfile-defined container. ELF,
              musl loader, Alpine apk toolchain.
              Completed and frozen at commit 6750ae2.
  macos       Native Apple Silicon macOS 26.0+. Mach-O,
              Apple libSystem, the locked official LLVM archive, and the Xcode SDK.

`family` selects the toolchain, relocation module, and binary-format checks.
Fields belonging to the other family are left empty; do not read
`musl_loader` on a macOS target or `deployment_target` on a Linux one.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass

LINUX_MUSL = "linux-musl"
MACOS = "macos"

FAMILIES = (LINUX_MUSL, MACOS)


class UnsupportedTargetError(Exception):
    """No target description exists for this machine/triple."""


@dataclass(frozen=True)
class Target:
    triple: str
    machine: str  # platform.machine() spelling
    family: str  # linux-musl | macos
    cpu_baseline_cflag: str  # explicit, recorded ISA floor
    openssl_configure_target: str  # `Configure <target>` string

    # linux-musl only
    alpine_arch: str = ""  # apk/Alpine architecture tag
    docker_platform: str = ""  # linux/amd64, linux/arm64, ...
    musl_loader: str = ""  # expected PT_INTERP value

    # macos only
    deployment_target: str = ""  # -mmacosx-version-min floor, e.g. "26.0"
    platform_tag_prefix: str = ""  # PEP 425 macOS tag prefix, e.g. "macosx_26_0"

    def __post_init__(self) -> None:
        if self.family not in FAMILIES:
            raise UnsupportedTargetError(f"{self.triple}: unknown family {self.family!r}")
        if self.family == LINUX_MUSL and not (self.alpine_arch and self.musl_loader):
            raise UnsupportedTargetError(f"{self.triple}: linux-musl target needs loader/arch")
        if self.family == MACOS and not self.deployment_target:
            raise UnsupportedTargetError(f"{self.triple}: macos target needs a deployment floor")

    @property
    def is_macos(self) -> bool:
        return self.family == MACOS


TARGETS: dict[str, Target] = {
    "x86_64-unknown-linux-musl": Target(
        triple="x86_64-unknown-linux-musl",
        machine="x86_64",
        family=LINUX_MUSL,
        cpu_baseline_cflag="-march=x86-64",
        openssl_configure_target="linux-x86_64",
        alpine_arch="x86_64",
        docker_platform="linux/amd64",
        musl_loader="/lib/ld-musl-x86_64.so.1",
    ),
    "aarch64-unknown-linux-musl": Target(
        triple="aarch64-unknown-linux-musl",
        machine="aarch64",
        family=LINUX_MUSL,
        cpu_baseline_cflag="-march=armv8-a",
        openssl_configure_target="linux-aarch64",
        alpine_arch="aarch64",
        docker_platform="linux/arm64",
        musl_loader="/lib/ld-musl-aarch64.so.1",
    ),
    # Apple Silicon only. `apple-m1` is clang 23's own default `-target-cpu`
    # for arm64-apple-macosx, made explicit so a toolchain change cannot move
    # the ISA floor silently; M1 is the oldest Apple Silicon, so this is the
    # narrowest baseline that still covers every supported machine.
    "aarch64-apple-darwin": Target(
        triple="aarch64-apple-darwin",
        machine="arm64",
        family=MACOS,
        cpu_baseline_cflag="-mcpu=apple-m1",
        openssl_configure_target="darwin64-arm64-cc",
        deployment_target="26.0",
        platform_tag_prefix="macosx_26_0",
    ),
}


def target_for_triple(triple: str) -> Target:
    try:
        return TARGETS[triple]
    except KeyError:
        raise UnsupportedTargetError(f"no target description for {triple!r}") from None


def native_target() -> Target:
    """The target matching the machine this process is actually running on.

    `machine` alone is ambiguous across families (aarch64 vs arm64 are the
    same silicon and both spellings appear), so the current OS decides which
    family is even eligible before the machine name is compared.
    """
    machine = platform.machine()
    family = MACOS if platform.system() == "Darwin" else LINUX_MUSL
    for target in TARGETS.values():
        if target.family == family and target.machine == machine:
            return target
    raise UnsupportedTargetError(
        f"no {family} target description for host machine {machine!r}"
    )
