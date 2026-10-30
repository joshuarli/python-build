from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from buildsys.generations import (
    ACTIVE,
    GENERATIONS,
    GenerationError,
    active_generation,
    publish_generation,
)

REPOSITORY = Path(__file__).resolve().parents[1]

CRASHING_PUBLISHER = textwrap.dedent(
    """
    import os, shutil, sys
    from pathlib import Path
    from buildsys.generations import publish_generation

    crash_at = int(sys.argv[1])
    target = Path(sys.argv[2])
    sources = {name: Path(path) for name, path in zip(sys.argv[3::2], sys.argv[4::2])}
    calls = 0

    def counted(real):
        def wrapper(*args, **kwargs):
            global calls
            calls += 1
            if calls == crash_at:
                os._exit(137)
            return real(*args, **kwargs)
        return wrapper

    for owner, name in ((os, "fsync"), (os, "replace"), (os, "rename"),
                        (os, "unlink"), (shutil, "rmtree")):
        setattr(owner, name, counted(getattr(owner, name)))
    publish_generation(target, sources)
    print(calls)
    """
)


def write_files(root: Path, contents: dict[str, bytes]) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, content in contents.items():
        paths[name] = root / name
        paths[name].write_bytes(content)
    return paths


def read_generation(target: Path) -> dict[str, bytes]:
    directory = active_generation(target)
    return {
        path.name: path.read_bytes()
        for path in directory.iterdir()
        if path.name != "GENERATION.json"
    }


class PublishGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.target = self.root / "dist" / "triple"
        self.first = {"archive.tar.gz": b"archive one", "artifact.json": b'{"n": 1}'}
        self.second = {"archive.tar.gz": b"archive two", "artifact.json": b'{"n": 2}'}

    def publish(self, contents: dict[str, bytes], label: str) -> str:
        return publish_generation(self.target, write_files(self.root / label, contents))

    def test_readers_get_the_published_files(self) -> None:
        self.publish(self.first, "a")
        self.assertEqual(read_generation(self.target), self.first)

    def test_new_publication_replaces_active_and_keeps_one_predecessor(self) -> None:
        a = self.publish(self.first, "a")
        b = self.publish(self.second, "b")
        self.assertNotEqual(a, b)
        self.assertEqual(read_generation(self.target), self.second)
        third = {"archive.tar.gz": b"archive three", "artifact.json": b"{}"}
        c = self.publish(third, "c")
        kept = {path.name for path in (self.target / GENERATIONS).iterdir()}
        self.assertEqual(kept, {b, c})

    def test_republishing_identical_bytes_is_idempotent(self) -> None:
        a = self.publish(self.first, "a")
        self.assertEqual(self.publish(self.first, "again"), a)
        self.assertEqual(read_generation(self.target), self.first)

    def test_reader_rejects_tampered_extra_and_missing_state(self) -> None:
        with self.assertRaises(GenerationError):
            active_generation(self.target)
        self.publish(self.first, "a")
        directory = active_generation(self.target)
        (directory / "artifact.json").write_bytes(b'{"n": 9}')
        with self.assertRaises(GenerationError):
            active_generation(self.target)
        (directory / "artifact.json").write_bytes(self.first["artifact.json"])
        (directory / "stray").write_bytes(b"x")
        with self.assertRaises(GenerationError):
            active_generation(self.target)
        (directory / "stray").unlink()
        (self.target / ACTIVE).write_text("../../etc\n")
        with self.assertRaises(GenerationError):
            active_generation(self.target)

    def test_invalid_inputs_are_rejected(self) -> None:
        sources = write_files(self.root / "s", {"ok": b"x"})
        for bad in ({}, {"../escape": sources["ok"]}, {"ACTIVE": sources["ok"]},
                    {".hidden": sources["ok"]}, {"missing": self.root / "none"}):
            with self.subTest(bad=list(bad)), self.assertRaises(GenerationError):
                publish_generation(self.target, bad)

    def crash_publishing(self, contents: dict[str, bytes], crash_at: int) -> subprocess.CompletedProcess:
        sources = write_files(self.root / f"crash-{crash_at}", contents)
        arguments = [str(item) for name, path in sources.items() for item in (name, path)]
        return subprocess.run(
            [sys.executable, "-c", CRASHING_PUBLISHER, str(crash_at), str(self.target), *arguments],
            cwd=REPOSITORY, capture_output=True, text=True, check=False,
        )

    def test_killing_the_publisher_at_any_step_leaves_one_complete_generation(self) -> None:
        self.publish(self.first, "a")
        clean = self.crash_publishing(self.second, 10**6)
        self.assertEqual(clean.returncode, 0, clean.stderr)
        steps = int(clean.stdout.strip())
        self.assertGreater(steps, 5)
        for crash_at in range(1, steps + 1):
            with self.subTest(crash_at=crash_at):
                shutil.rmtree(self.target)
                self.publish(self.first, "a")
                crashed = self.crash_publishing(self.second, crash_at)
                self.assertEqual(crashed.returncode, 137, crashed.stderr)
                self.assertIn(read_generation(self.target), (self.first, self.second))
                self.publish(self.second, "retry")
                self.assertEqual(read_generation(self.target), self.second)
                leftovers = sorted(
                    path.name for path in self.target.iterdir()
                    if path.name not in {ACTIVE, GENERATIONS, ".publish.lock"}
                )
                self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
