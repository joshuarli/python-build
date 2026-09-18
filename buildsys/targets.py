"""Target description: the one place architecture-specific data lives.

Plan Section 12: "Linux aarch64 should prefer native execution and change
target/toolchain data plus genuinely architecture-specific handling, rather
than introducing premature cross compilation." Every recipe, the CPython
configure policy, and validation share one dependency graph, one Toolchain,
and one packaging pipeline; only the handful of values below differ by
machine. The running interpreter's own `platform.machine()` is what's
actually true inside a given container (including a QEMU-emulated one, which
reports the emulated architecture, not the host's) — target selection reads
that rather than trusting an external flag that could disagree with reality.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass


class UnsupportedTargetError(Exception):
    """No target description exists for this machine/triple."""


@dataclass(frozen=True)
class Target:
    triple: str
    machine: str  # platform.machine() spelling
    alpine_arch: str  # apk/Alpine architecture tag
    docker_platform: str  # linux/amd64, linux/arm64, ...
    cpu_baseline_cflag: str  # explicit, recorded ISA floor (plan 5.1/7)
    openssl_configure_target: str  # `Configure <target>` string
    musl_loader: str  # expected PT_INTERP value


TARGETS: dict[str, Target] = {
    "x86_64-unknown-linux-musl": Target(
        triple="x86_64-unknown-linux-musl",
        machine="x86_64",
        alpine_arch="x86_64",
        docker_platform="linux/amd64",
        cpu_baseline_cflag="-march=x86-64",
        openssl_configure_target="linux-x86_64",
        musl_loader="/lib/ld-musl-x86_64.so.1",
    ),
    "aarch64-unknown-linux-musl": Target(
        triple="aarch64-unknown-linux-musl",
        machine="aarch64",
        alpine_arch="aarch64",
        docker_platform="linux/arm64",
        cpu_baseline_cflag="-march=armv8-a",
        openssl_configure_target="linux-aarch64",
        musl_loader="/lib/ld-musl-aarch64.so.1",
    ),
}


def target_for_triple(triple: str) -> Target:
    try:
        return TARGETS[triple]
    except KeyError:
        raise UnsupportedTargetError(f"no target description for {triple!r}") from None


def native_target() -> Target:
    """The target matching the machine this process is actually running on."""
    machine = platform.machine()
    for target in TARGETS.values():
        if target.machine == machine:
            return target
    raise UnsupportedTargetError(f"no target description for host machine {machine!r}")
