"""Tests for hash-locked benchmark downloads and external prefix preparation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from benchmarks.harness.inputs import InputError, fetch_inputs, load_lock, prepare_site, resolve_pbs


def _make_wheel(path: Path, package: str, version: str, source: str) -> bytes:
    dist_info = f"{package}-{version}.dist-info"
    with ZipFile(path, "w") as archive:
        archive.writestr(f"{package}/__init__.py", f"VALUE = {source!r}\n")
        archive.writestr(
            f"{dist_info}/METADATA",
            f"Metadata-Version: 2.1\nName: {package}\nVersion: {version}\n\n",
        )
        archive.writestr(f"{dist_info}/WHEEL", "Wheel-Version: 1.0\nRoot-Is-Purelib: true\n")
    return path.read_bytes()


def _lock_record(package: str, version: str, filename: str, data: bytes, groups: list[str]) -> dict[str, object]:
    return {
        "name": package,
        "version": version,
        "url": f"https://example.invalid/{filename}",
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "license": "MIT",
        "purpose": "Synthetic test workload input.",
        "filename": filename,
        "kind": "wheel",
        "wheel_tags": ["py3-none-any"],
        "groups": groups,
    }


class BenchmarkInputTests(unittest.TestCase):
    def test_repository_lock_has_complete_linux_amd64_wheel_identity(self) -> None:
        lock = load_lock()

        self.assertEqual(lock.target["architecture"], "x86_64")
        self.assertEqual(lock.target["wheel_platform"], "musllinux_1_2_x86_64")
        self.assertIn("macros", lock.groups)
        self.assertIn("pyperformance", lock.groups)
        self.assertIn("memray", lock.groups)
        self.assertGreater(len(lock.inputs), 50)
        for item in lock.inputs:
            self.assertEqual(len(item.sha256), 64)
            self.assertGreater(item.size, 0)
            self.assertTrue(item.license)
            self.assertTrue(item.purpose)
            if item.kind == "wheel":
                self.assertTrue(item.wheel_tags)

    def test_fastapi_lock_has_the_complete_pydantic_v2_runtime_closure(self) -> None:
        lock = load_lock()
        packages = {
            item.name.lower().replace("_", "-"): item
            for item in lock.inputs
        }

        self.assertEqual(packages["fastapi"].version, "0.121.0")
        self.assertEqual(packages["pydantic"].version, "2.13.5")
        self.assertEqual(packages["pydantic-core"].version, "2.46.5")
        self.assertEqual(packages["annotated-types"].version, "0.8.0")
        self.assertEqual(packages["typing-inspection"].version, "0.4.4")
        self.assertEqual(packages["typing-extensions"].version, "4.16.0")
        self.assertIn(
            "cp314-cp314-musllinux_1_1_x86_64",
            packages["pydantic-core"].wheel_tags,
        )
        for package in (
            "fastapi", "pydantic", "pydantic-core", "annotated-types",
            "typing-inspection", "typing-extensions",
        ):
            self.assertTrue({"macros", "pyperformance"}.issubset(packages[package].groups))

    def test_fetch_all_families_keeps_different_locked_versions_separate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wheelhouse = root / "wheelhouse"
            wheelhouse.mkdir()
            artifacts = [
                ("bootrunner", "1.0", "bootrunner-1.0-py3-none-any.whl", ["core"], "boot"),
                ("demo", "1.0", "demo-1.0-py3-none-any.whl", ["macros"], "macro"),
                ("demo", "2.0", "demo-2.0-py3-none-any.whl", ["pyperformance"], "standard"),
            ]
            inputs = []
            for package, version, filename, groups, contents in artifacts:
                path = wheelhouse / filename
                data = _make_wheel(path, package, version, contents)
                inputs.append(_lock_record(package, version, filename, data, groups))
            raw_lock = {
                "schema_version": 1,
                "target": {"os": "linux", "architecture": "x86_64", "libc": "musl"},
                "groups": {
                    "core": {"include_groups": [], "packages": []},
                    "macros": {"include_groups": ["core"], "packages": ["demo==1.0"]},
                    "pyperformance": {"include_groups": ["core"], "packages": ["demo==2.0"]},
                },
                "inputs": inputs,
            }
            lock_path = root / "inputs.lock.json"
            lock_path.write_text(json.dumps(raw_lock))
            lock = load_lock(lock_path)

            # Fetch accepts both frozen environments; conflict checks apply only
            # when one environment is assembled for an actual workload.
            self.assertEqual(fetch_inputs(lock, cache_dir=wheelhouse), wheelhouse)
            prepared = prepare_site(
                "/path/to/unused/python",
                root / "prepared-macros",
                groups={"macros"},
                wheelhouse=wheelhouse,
                lock=lock,
            )

            self.assertEqual(prepared.pip_packages, ("demo==1.0",))
            self.assertEqual(
                (prepared.site_packages / "demo" / "__init__.py").read_text(),
                "VALUE = 'macro'\n",
            )
            self.assertTrue((prepared.wheelhouse / "demo-1.0-py3-none-any.whl").is_file())
            self.assertFalse((prepared.wheelhouse / "demo-2.0-py3-none-any.whl").exists())
            self.assertIsNone(prepared.benchmark_root)

    def test_prepare_rejects_tampered_cache_and_unsafe_wheel_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "wheelhouse"
            cache.mkdir()
            filename = "demo-1.0-py3-none-any.whl"
            wheel = cache / filename
            data = _make_wheel(wheel, "demo", "1.0", "safe")
            input_record = _lock_record("demo", "1.0", filename, data, ["macros"])
            lock_path = root / "inputs.lock.json"
            lock_path.write_text(json.dumps({
                "schema_version": 1,
                "target": {"os": "linux", "architecture": "x86_64"},
                "groups": {
                    "core": {"include_groups": [], "packages": []},
                    "macros": {"include_groups": ["core"], "packages": ["demo==1.0"]},
                },
                "inputs": [input_record],
            }))
            lock = load_lock(lock_path)
            wheel.write_bytes(b"tampered")
            with self.assertRaises(InputError):
                prepare_site("unused", root / "tampered", groups="macros", wheelhouse=cache, lock=lock)

            unsafe = cache / filename
            with ZipFile(unsafe, "w") as archive:
                archive.writestr("../outside.py", "VALUE = 'escaped'\n")
            unsafe_data = unsafe.read_bytes()
            input_record.update({
                "sha256": hashlib.sha256(unsafe_data).hexdigest(),
                "size": len(unsafe_data),
            })
            lock_path.write_text(json.dumps({
                "schema_version": 1,
                "target": {"os": "linux", "architecture": "x86_64"},
                "groups": {
                    "core": {"include_groups": [], "packages": []},
                    "macros": {"include_groups": ["core"], "packages": ["demo==1.0"]},
                },
                "inputs": [input_record],
            }))
            unsafe_lock = load_lock(lock_path)
            with self.assertRaises(InputError):
                prepare_site("unused", root / "unsafe", groups="macros", wheelhouse=cache, lock=unsafe_lock)
            self.assertFalse((root / "outside.py").exists())
            self.assertFalse((root / "unsafe").exists())

    def test_pbs_resolution_is_offline_and_hash_checks_cached_archive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = b"pinned test archive"
            digest = hashlib.sha256(source).hexdigest()
            filename = "cpython-3.14.6+20260610-x86_64-unknown-linux-musl-install_only_stripped.tar.gz"
            source_lock = root / "sources.lock.json"
            source_lock.write_text(json.dumps({"inputs": [{
                "name": "reference-pbs",
                "version": "20260610",
                "url": f"https://example.invalid/{filename}",
                "sha256": digest,
                "role": "reference",
                "license": "Python-2.0",
                "purpose": "comparison-only test input",
            }]}))
            cache = root / "references"
            cache.mkdir()
            (cache / filename).write_bytes(source)

            artifact = resolve_pbs(source_lock, cache_dir=cache)
            self.assertEqual(artifact.path, cache / filename)
            self.assertEqual(artifact.sha256, digest)
            (cache / filename).write_bytes(b"tampered")
            with self.assertRaises(InputError):
                resolve_pbs(source_lock, cache_dir=cache)

    def test_pbs_resolution_selects_the_requested_target_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            linux_archive = b"linux reference"
            macos_archive = b"macOS reference"
            records = []
            for target, name, filename, contents in (
                (
                    "x86_64-unknown-linux-musl",
                    "reference-pbs",
                    "cpython-3.14.6+20260610-x86_64-unknown-linux-musl-install_only_stripped.tar.gz",
                    linux_archive,
                ),
                (
                    "aarch64-apple-darwin",
                    "reference-pbs-aarch64-apple-darwin",
                    "cpython-3.14.6+20260610-aarch64-apple-darwin-install_only.tar.gz",
                    macos_archive,
                ),
            ):
                records.append({
                    "name": name,
                    "target": target,
                    "version": "20260610",
                    "url": f"https://example.invalid/{filename}",
                    "sha256": hashlib.sha256(contents).hexdigest(),
                    "role": "reference",
                    "license": "Python-2.0",
                    "purpose": "comparison-only test input",
                })
            source_lock = root / "sources.lock.json"
            source_lock.write_text(json.dumps({"inputs": records}))
            cache = root / "references"
            cache.mkdir()
            for record, contents in zip(records, (linux_archive, macos_archive)):
                (cache / Path(record["url"]).name).write_bytes(contents)

            artifact = resolve_pbs(
                source_lock,
                cache_dir=cache,
                target="aarch64-apple-darwin",
            )

        self.assertEqual(artifact.path.name, records[1]["url"].rsplit("/", 1)[1])
        self.assertEqual(artifact.sha256, records[1]["sha256"])


if __name__ == "__main__":
    unittest.main()
