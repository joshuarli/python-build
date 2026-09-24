"""Pinned source-analysis and bytecode-production benchmark workloads.

Run one workload with ``python -m benchmarks.workloads.tooling <scenario>``.
All source inputs are checked-in fixtures. The workload measures only its
operation loop, then checks pass counts and output digests before emitting a
single JSON result line.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import py_compile
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "tooling"
PYTHON_CORPUS = FIXTURE_ROOT / "python_corpus"
C_CORPUS = FIXTURE_ROOT / "c_corpus"
PYLINT_VERSION = "4.0.9"
PYCPARSER_VERSION = "3.0"
SCENARIOS = ("pylint_source", "pycparser_source", "compileall_source")


class WorkloadError(RuntimeError):
    """Raised when a workload cannot complete or validate its result."""


@dataclass(frozen=True, slots=True)
class WorkloadResult:
    """Stable correctness data and measured operation-loop duration."""

    operation_count: int
    digest: str
    elapsed_seconds: float

    def as_json(self) -> dict[str, object]:
        """Return the result fields consumed by the benchmark controller."""
        return {
            "operation_count": self.operation_count,
            "digest": self.digest,
            "elapsed_seconds": self.elapsed_seconds,
        }


def _positive_iterations(value: str) -> int:
    """Parse the CLI iteration count and reject empty work loops."""
    try:
        iterations = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("iterations must be an integer") from error
    if iterations < 1:
        raise argparse.ArgumentTypeError("iterations must be positive")
    return iterations


def _sha256_json(value: object) -> str:
    """Hash a JSON value using a stable compact encoding."""
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _python_sources() -> tuple[Path, ...]:
    """Find the immutable Python fixture files in lexical order."""
    sources = tuple(sorted(PYTHON_CORPUS.rglob("*.py")))
    if len(sources) < 20:
        raise WorkloadError(f"Python fixture corpus is incomplete: {len(sources)} files")
    return sources


def _c_inputs() -> tuple[tuple[str, str], ...]:
    """Read and decode all preprocessed C inputs before starting the timer."""
    paths = tuple(sorted(C_CORPUS.glob("*.i")))
    if len(paths) < 3:
        raise WorkloadError(f"C fixture corpus needs at least three files, got {len(paths)}")
    inputs: list[tuple[str, str]] = []
    for path in paths:
        payload = path.read_bytes()
        if len(payload) < 100_000:
            raise WorkloadError(f"C fixture is unexpectedly small: {path.name}")
        try:
            source = payload.decode("utf-8")
        except UnicodeDecodeError as error:
            raise WorkloadError(f"C fixture is not UTF-8: {path.name}") from error
        if "#include" in source or "#define" in source:
            raise WorkloadError(f"C fixture is not preprocessed: {path.name}")
        inputs.append((path.name, source))
    return tuple(inputs)


def _normalize_pylint_messages(payload: bytes, cwd: Path) -> tuple[dict[str, object], ...]:
    """Normalize pylint JSON records so only deterministic diagnostics remain."""
    try:
        messages = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WorkloadError("pylint did not return valid JSON diagnostics") from error
    if not isinstance(messages, list):
        raise WorkloadError("pylint JSON result must be a list")
    normalized: list[dict[str, object]] = []
    for message in messages:
        if not isinstance(message, dict):
            raise WorkloadError("pylint returned a malformed diagnostic")
        raw_path = str(message.get("path", ""))
        path = Path(raw_path)
        if path.is_absolute():
            try:
                normalized_path = path.resolve().relative_to(PYTHON_CORPUS.resolve()).as_posix()
            except ValueError:
                normalized_path = path.name
        else:
            candidate = (cwd / path).resolve()
            try:
                normalized_path = candidate.relative_to(PYTHON_CORPUS.resolve()).as_posix()
            except ValueError:
                normalized_path = Path(raw_path.replace("\\", "/")).as_posix()
        normalized.append(
            {
                "path": normalized_path,
                "module": str(message.get("module", "")),
                "obj": str(message.get("obj", "")),
                "line": int(message.get("line") or 0),
                "column": int(message.get("column") or 0),
                "end_line": int(message.get("endLine") or 0),
                "end_column": int(message.get("endColumn") or 0),
                "message_id": str(message.get("message-id", "")),
                "symbol": str(message.get("symbol", "")),
                "type": str(message.get("type", "")),
                "confidence": str(message.get("confidence", "")),
                "message": str(message.get("message", "")),
            }
        )
    normalized.sort(
        key=lambda item: (
            str(item["path"]),
            int(item["line"]),
            int(item["column"]),
            str(item["message_id"]),
            str(item["symbol"]),
            str(item["message"]),
        )
    )
    if any(message["type"] in {"fatal", "error"} for message in normalized):
        raise WorkloadError("pylint reported a fatal or error diagnostic")
    return tuple(normalized)


def pylint_source(iterations: int) -> WorkloadResult:
    """Run the pinned pylint command across the checked-in Python package."""
    try:
        actual_version = importlib.metadata.version("pylint")
    except importlib.metadata.PackageNotFoundError as error:
        raise WorkloadError("pylint is not present in the prepared benchmark site") from error
    if actual_version != PYLINT_VERSION:
        raise WorkloadError(f"expected pylint {PYLINT_VERSION}, found {actual_version}")

    sources = _python_sources()
    cwd = PYTHON_CORPUS
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    command = (
        sys.executable,
        "-m",
        "pylint",
        "--output-format=json",
        f"--rcfile={os.devnull}",
        "--persistent=n",
        "--reports=n",
        "--score=n",
        "--jobs=1",
        "--recursive=y",
        "catalog_service",
    )
    digests: list[str] = []
    message_count: int | None = None
    elapsed = 0.0
    with tempfile.TemporaryDirectory(prefix="pylint-source-") as pylint_home:
        environment["PYLINTHOME"] = pylint_home
        for _ in range(iterations):
            started = time.perf_counter()
            completed = subprocess.run(
                command,
                cwd=cwd,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            elapsed += time.perf_counter() - started
            if completed.returncode < 0 or completed.returncode & 32:
                detail = completed.stderr.decode("utf-8", errors="replace").strip()
                raise WorkloadError(f"pylint failed to run: {detail or completed.returncode}")
            messages = _normalize_pylint_messages(completed.stdout, cwd)
            current_digest = _sha256_json(
                {
                    "source_count": len(sources),
                    "messages": messages,
                }
            )
            if message_count is not None and len(messages) != message_count:
                raise WorkloadError("pylint diagnostic count changed between passes")
            message_count = len(messages)
            digests.append(current_digest)
    if not digests or any(digest != digests[0] for digest in digests[1:]):
        raise WorkloadError("pylint diagnostics changed between passes")
    return WorkloadResult(len(sources) * iterations, digests[0], elapsed)


def _summarize_c_ast(roots: Sequence[tuple[str, Any]]) -> tuple[int, str]:
    """Count AST nodes and hash node types, attributes, and child ordering."""
    count = 0
    digest = hashlib.sha256()
    for filename, root in roots:
        digest.update(filename.encode("utf-8"))
        digest.update(b"\0")
        pending = [root]
        while pending:
            node = pending.pop()
            children = tuple(node.children())
            attributes = [getattr(node, name) for name in node.attr_names]
            record = [
                type(node).__name__,
                attributes,
                [name for name, _ in children],
            ]
            encoded = json.dumps(record, ensure_ascii=True, separators=(",", ":"))
            digest.update(encoded.encode("utf-8"))
            digest.update(b"\n")
            pending.extend(child for _, child in reversed(children))
            count += 1
    return count, digest.hexdigest()


def pycparser_source(iterations: int) -> WorkloadResult:
    """Parse preloaded C translation units and verify their AST structure."""
    try:
        actual_version = importlib.metadata.version("pycparser")
    except importlib.metadata.PackageNotFoundError as error:
        raise WorkloadError("pycparser is not present in the prepared benchmark site") from error
    if actual_version != PYCPARSER_VERSION:
        raise WorkloadError(f"expected pycparser {PYCPARSER_VERSION}, found {actual_version}")
    from pycparser import c_parser

    inputs = _c_inputs()
    elapsed = 0.0
    expected: tuple[int, str] | None = None
    for _ in range(iterations):
        roots: list[tuple[str, Any]] = []
        started = time.perf_counter()
        for filename, source in inputs:
            tree = c_parser.CParser().parse(source, filename=filename)
            roots.append((filename, tree))
        elapsed += time.perf_counter() - started
        current = _summarize_c_ast(roots)
        if current[0] < 10_000:
            raise WorkloadError(f"C AST is unexpectedly small: {current[0]} nodes")
        if expected is not None and current != expected:
            raise WorkloadError("pycparser AST count or digest changed between passes")
        expected = current
        roots.clear()
    if expected is None:
        raise WorkloadError("pycparser ran no parse passes")
    node_count, digest = expected
    return WorkloadResult(node_count * iterations, digest, elapsed)


def _digest_compiled_sources(output_root: Path, sources: Iterable[Path]) -> tuple[int, str]:
    """Verify fresh `.pyc` files and hash them by stable source-relative path."""
    digest = hashlib.sha256()
    count = 0
    for source in sources:
        relative = source.relative_to(PYTHON_CORPUS).as_posix()
        output = importlib.util.cache_from_source(str(source))
        compiled = Path(output)
        if not compiled.is_file() or not compiled.is_relative_to(output_root):
            raise WorkloadError(f"compileall did not produce a fresh bytecode file for {relative}")
        payload = compiled.read_bytes()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(payload)
        count += 1
    actual_outputs = tuple(output_root.rglob("*.pyc"))
    if len(actual_outputs) != count:
        raise WorkloadError(
            f"compileall produced {len(actual_outputs)} files; expected exactly {count}"
        )
    return count, digest.hexdigest()


def compileall_source(iterations: int) -> WorkloadResult:
    """Compile the full fixture package into a fresh pycache prefix per pass."""
    sources = _python_sources()
    import compileall

    output_digests: list[str] = []
    elapsed = 0.0
    with tempfile.TemporaryDirectory(prefix="compileall-source-") as temporary:
        output_root = Path(temporary)
        outputs = tuple(output_root / f"pass-{index:04d}" for index in range(iterations))
        for output in outputs:
            output.mkdir()
        previous_prefix = sys.pycache_prefix
        try:
            for output in outputs:
                sys.pycache_prefix = str(output)
                started = time.perf_counter()
                succeeded = compileall.compile_dir(
                    str(PYTHON_CORPUS),
                    force=True,
                    quiet=2,
                    workers=1,
                    invalidation_mode=py_compile.PycInvalidationMode.CHECKED_HASH,
                    stripdir=str(PYTHON_CORPUS),
                    prependdir="catalog_service",
                )
                elapsed += time.perf_counter() - started
                if not succeeded:
                    raise WorkloadError("compileall failed to compile the Python fixture")
                count, digest = _digest_compiled_sources(output, sources)
                if count != len(sources):
                    raise WorkloadError(
                        f"compileall compiled {count} modules; expected {len(sources)}"
                    )
                output_digests.append(digest)
        finally:
            sys.pycache_prefix = previous_prefix
    if not output_digests or any(value != output_digests[0] for value in output_digests[1:]):
        raise WorkloadError("compileall output digest changed between fresh destinations")
    return WorkloadResult(len(sources) * iterations, output_digests[0], elapsed)


_RUNNERS: dict[str, Callable[[int], WorkloadResult]] = {
    "pylint_source": pylint_source,
    "pycparser_source": pycparser_source,
    "compileall_source": compileall_source,
}


def run_scenario(name: str, iterations: int = 1) -> WorkloadResult:
    """Run and validate one named workload scenario."""
    if name not in _RUNNERS:
        raise ValueError(f"unknown tooling scenario: {name}")
    if iterations < 1:
        raise ValueError("iterations must be positive")
    return _RUNNERS[name](iterations)


def main(arguments: Sequence[str] | None = None) -> int:
    """CLI entry point with JSON written as the final stdout line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=SCENARIOS)
    parser.add_argument("--iterations", type=_positive_iterations, default=1)
    options = parser.parse_args(arguments)
    try:
        result = run_scenario(options.scenario, options.iterations)
    except WorkloadError as error:
        print(f"tooling workload error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result.as_json(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
