"""Sealed execution on macOS via `sandbox-exec`.

Linux containment here is a container network namespace; macOS has no such
thing for Mach-O builds, so the boundary is a `sandbox-exec` profile. Two
properties matter and both are enforced rather than asserted:

  * the network is denied at the process-sandbox level, not by asking the
    build nicely (`--offline` that merely skips a downloader is not a
    boundary), and
  * the only writable locations are declared work/output directories.

What this is *not*: a container. A sandboxed process shares the host kernel
and filesystem namespace with everything else, so this is weaker containment
than the Linux targets have. Reports describe this boundary accurately; the
network denial is checked with a live listener rather than assumed from the
profile configuration.

`network_boundary_selftest` is the load-bearing check: it runs the same
probe inside and outside the profile against a listener this process owns,
so a pass means "the sandbox denied it" and not "there was no network".
"""

from __future__ import annotations

import socket
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path

SANDBOX_EXEC = "/usr/bin/sandbox-exec"
# network-outbound and network-inbound are denied separately; denying
# `network*` covers UNIX sockets too, which would otherwise let a sandboxed
# process talk to a host daemon.
PROFILE_TEMPLATE = """(version 1)
(deny default)

; Processes and the syscalls a compiler driver needs to do its job.
(allow process-fork)
(allow process-exec*)
(allow signal (target self))
(allow sysctl-read)
(allow mach-lookup)
(allow ipc-posix-shm)
; POSIX named semaphores. CPython's configure *executes* a sem_open probe, so
; denying this does not fail the build — it quietly disables POSIX_SEMAPHORES
; and removes SemLock from _multiprocessing, producing a worse interpreter
; than an unsealed build of the same sources.
(allow ipc-posix-sem)

; Reads are permitted broadly: the threat here is escaping the build tree or
; reaching the network, not reading. Writes are what is constrained.
(allow file-read*)

{write_rules}
(allow file-write* (literal "/dev/null") (literal "/dev/dtracehelper"))
(allow file-write-data (literal "/dev/tty"))

(deny network*)
"""


class SandboxError(Exception):
    """The sandbox could not be used, or the boundary did not hold."""


def available() -> bool:
    return Path(SANDBOX_EXEC).is_file()


def _darwin_user_temp_dir() -> str | None:
    """The per-user scratch directory macOS hands out via confstr."""
    try:
        result = subprocess.run(
            ["getconf", "DARWIN_USER_TEMP_DIR"], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    path = result.stdout.strip()
    return path if result.returncode == 0 and path.startswith("/") else None


@dataclass
class SealedRun:
    """One sealed execution: what it may write, where it runs, what it sees."""

    write_paths: list[Path] = field(default_factory=list)
    home: Path | None = None

    @property
    def tmpdir(self) -> Path:
        return (self.write_paths[0] / "tmp") if self.write_paths else Path("/tmp")

    def prepare(self) -> None:
        """Create the directories the profile declares writable.

        Compilers write scratch files to `TMPDIR`; declaring that path in the
        profile while leaving it non-existent produces "unable to make
        temporary file" from clang rather than a sandbox denial, which reads
        like a toolchain problem instead of a setup one.
        """
        for path in self.write_paths:
            Path(path).mkdir(parents=True, exist_ok=True)
        if self.write_paths:
            self.tmpdir.mkdir(parents=True, exist_ok=True)
        if self.home is not None:
            Path(self.home).mkdir(parents=True, exist_ok=True)

    def profile(self) -> str:
        rules = []
        for path in self.write_paths:
            resolved = Path(path).resolve()
            rules.append(f'(allow file-write* (subpath "{resolved}"))')
        # `ld` caches a database under the per-user Darwin temp directory and
        # ignores TMPDIR when doing so (it asks confstr directly). Denying it
        # is non-fatal but noisy, and a future linker could make it fatal, so
        # the directory is allowed explicitly rather than left to chance.
        # This is the OS's per-user scratch area, not the project tree or the
        # user's home — the widening is named here and in `describe()`.
        scratch = _darwin_user_temp_dir()
        if scratch:
            # Strip the trailing slash: `subpath` matches path components, so
            # "/tmp/x/" would not cover "/tmp/x/file". Both the verbatim and
            # the symlink-resolved form are allowed because /var is a symlink
            # to /private/var and the sandbox matches on the resolved path.
            trimmed = scratch.rstrip("/")
            for candidate in {trimmed, str(Path(trimmed).resolve())}:
                rules.append(f'(allow file-write* (subpath "{candidate}"))')
        return PROFILE_TEMPLATE.format(write_rules="\n".join(rules))

    def environment(self, base: dict[str, str] | None = None) -> dict[str, str]:
        """A controlled environment: allowlist, not inherit-and-delete.

        An inherited variable that redirects a search path (DYLD_*, PATH,
        PYTHON*, SDKROOT) would silently change what gets built, so the
        sealed environment starts from a fixed set instead of the host's.
        """
        env = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(self.home) if self.home else "/nonexistent",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TZ": "UTC",
            "SHELL": "/bin/sh",
            "TMPDIR": str(self.tmpdir),
            "SOURCE_DATE_EPOCH": "1704067200",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
        }
        if base:
            env.update(base)
        return env

    def run(
        self,
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        log: Path | None = None,
    ) -> subprocess.CompletedProcess:
        self.prepare()
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".sb", delete=False, dir=self.write_paths[0] if self.write_paths else None
        )
        try:
            handle.write(self.profile())
            handle.close()
            full = [SANDBOX_EXEC, "-f", handle.name, *command]
            if log is not None:
                log.parent.mkdir(parents=True, exist_ok=True)
                with log.open("w") as out:
                    result = subprocess.run(
                        full, cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT
                    )
                return result
            return subprocess.run(full, cwd=cwd, env=env, capture_output=True, text=True)
        finally:
            Path(handle.name).unlink(missing_ok=True)


_PROBE = """
import socket, sys
sock = socket.socket()
sock.settimeout(5)
sock.connect(("127.0.0.1", int(sys.argv[1])))
sock.sendall(b"ping")
sock.close()
print("CONNECTED")
"""


def network_boundary_selftest(python: Path, workdir: Path) -> dict:
    """Prove the profile's network denial is real, not merely unexercised.

    A listener is opened on loopback by *this* process, then the same probe
    is run twice: once unsandboxed (which must succeed, else the test proves
    nothing) and once inside the profile (which must fail). Loopback is used
    deliberately so the result does not depend on the host having any
    external connectivity.
    """
    if not available():
        raise SandboxError(f"{SANDBOX_EXEC} is not present")
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    probe = workdir / "network_probe.py"
    probe.write_text(_PROBE)

    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(4)
    port = listener.getsockname()[1]
    accepted = []

    def accept_loop() -> None:
        listener.settimeout(20)
        while len(accepted) < 2:
            try:
                conn, _ = listener.accept()
            except OSError:
                return
            accepted.append(1)
            conn.close()

    thread = threading.Thread(target=accept_loop, daemon=True)
    thread.start()

    outside = subprocess.run(
        [str(python), str(probe), str(port)], capture_output=True, text=True
    )
    sealed = SealedRun(write_paths=[workdir], home=workdir / "home")
    inside = sealed.run([str(python), str(probe), str(port)], cwd=workdir,
                        env=sealed.environment())

    listener.close()
    thread.join(timeout=5)

    return {
        "probe": "tcp connect to a loopback listener owned by the validating process",
        "unsandboxed_connected": "CONNECTED" in outside.stdout,
        "sandboxed_connected": "CONNECTED" in inside.stdout,
        "sandboxed_output": (inside.stdout + inside.stderr).strip()[:300],
        "ok": "CONNECTED" in outside.stdout and "CONNECTED" not in inside.stdout,
    }


def describe() -> dict:
    """What the containment actually is, for the provenance record."""
    return {
        "mechanism": "sandbox-exec",
        "path": SANDBOX_EXEC,
        "present": available(),
        "isolation": "process sandbox sharing the host kernel and filesystem; "
                     "weaker than the Linux targets' container boundary",
        "network": "denied by profile (deny network*), verified by self-test",
        "filesystem": "writes restricted to declared output directories plus the "
                      "per-user Darwin temp directory that the linker's cache needs; "
                      "reads are not restricted",
    }
