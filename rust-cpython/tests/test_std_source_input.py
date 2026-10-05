"""The source-built standard library has a distinct verified archive owner."""

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import tarfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import perf

lb = perf.lb


class StdSourceInputTests(unittest.TestCase):
    def setUp(self):
        self.document = json.loads(lb.SOURCE_LOCK.read_text())
        self.document['inputs'] = [e for e in self.document['inputs']
                                   if e['name'] == 'cpython-rust']
        self.document['rust_std_source'] = {
            'version': '1.100.0-nightly (574ff7d98 2026-09-14)',
            'compiler_revision': '574ff7d98bd6d037e5236a8453029173b32631fd',
            'library_cargo_lock_sha256': hashlib.sha256(b'locked library\n').hexdigest(),
            'license': 'MIT OR Apache-2.0',
        }
        self.std_entry = {
            'name': 'rust-std-src',
            'version': self.document['rust_std_source']['version'],
            'url': 'https://static.rust-lang.org/dist/2026-09-15/rust-src-nightly.tar.xz',
            'sha256': 'd' * 64, 'size': 5927464, 'role': 'build-source',
            'target': lb.MACOS_TARGET, 'license': 'MIT OR Apache-2.0',
        }
        self.document['inputs'].append(self.std_entry)

    def lock(self, root):
        path = root / 'sources.lock.json'
        path.write_text(json.dumps(self.document))
        return mock.patch.object(lb, 'SOURCE_LOCK', path)

    def extraction(self, root):
        archive = root / 'rust-src-nightly'
        library = archive / 'rust-src/lib/rustlib/src/rust/library'
        library.mkdir(parents=True)
        (archive / 'version').write_text(self.document['rust_std_source']['version'])
        (archive / 'git-commit-hash').write_text(
            self.document['rust_std_source']['compiler_revision'])
        (library / 'Cargo.lock').write_bytes(b'locked library\n')
        for name in ('std', 'core', 'alloc', 'panic_abort'):
            (library / name).mkdir()
            (library / name / 'Cargo.toml').write_text('[package]\nname="'+name+'"\n')
        return archive, library

    def test_named_input_preserves_cpython_selection_when_reordered(self):
        self.document['inputs'].reverse()
        with tempfile.TemporaryDirectory() as tmp, self.lock(Path(tmp)):
            metadata, entry = lb._read_lock()
            self.assertEqual(entry.name, 'cpython-rust')
            self.assertEqual(entry.version, metadata['version'])
            metadata, entry = lb._read_rust_std_lock()
            self.assertEqual(entry.name, 'rust-std-src')
            self.assertEqual(metadata['compiler_revision'],
                             '574ff7d98bd6d037e5236a8453029173b32631fd')

    def test_missing_std_does_not_fall_back_to_cpython(self):
        self.document['inputs'].pop()
        with tempfile.TemporaryDirectory() as tmp, self.lock(Path(tmp)):
            self.assertEqual(lb._read_lock()[1].name, 'cpython-rust')
            with self.assertRaises(lb.LaneError):
                lb._read_rust_std_lock()

    def test_unknown_or_duplicate_source_is_rejected(self):
        for name in ('unexpected-source', 'rust-std-src'):
            with self.subTest(name=name):
                entry = copy.deepcopy(self.std_entry)
                entry['name'] = name
                self.document['inputs'].append(entry)
                with tempfile.TemporaryDirectory() as tmp, self.lock(Path(tmp)):
                    with self.assertRaises(lb.LaneError):
                        lb._read_lock()
                self.document['inputs'].pop()

    def test_cpython_metadata_mismatch_is_still_rejected(self):
        self.document['inputs'][0]['version'] = 'wrong'
        with tempfile.TemporaryDirectory() as tmp, self.lock(Path(tmp)):
            with self.assertRaises(lb.LaneError):
                lb._read_lock()

    def test_std_metadata_and_input_must_agree(self):
        for field, value in [('version', 'wrong'), ('role', 'reference'),
                             ('target', lb.LINUX_TARGET), ('license', 'wrong')]:
            original = self.std_entry[field]
            self.std_entry[field] = value
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp, \
                    self.lock(Path(tmp)):
                with self.assertRaises(lb.LaneError):
                    lb._read_rust_std_lock()
            self.std_entry[field] = original

    def test_extraction_requires_named_verified_archive_before_source_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _archive, library = self.extraction(root / 'extracted')
            with self.lock(root), mock.patch.object(lb.Cache, 'require',
                    return_value=root / 'verified.blob') as require, \
                    mock.patch.object(lb, 'safe_extract',
                        return_value=root / 'extracted') as extract:
                self.assertEqual(lb._extract_rust_std_source(root / 'destination'), library)
                self.assertEqual(require.call_args.args[0].name, 'rust-std-src')
                extract.assert_called_once_with(root / 'verified.blob', root / 'destination')

    def test_invalid_cache_never_extracts_or_reuses_existing_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / 'destination'
            self.extraction(destination)
            with self.lock(root), mock.patch.object(lb.Cache, 'require',
                    side_effect=lb.InputError('digest mismatch')), \
                    mock.patch.object(lb, 'safe_extract') as extract:
                with self.assertRaises(lb.InputError):
                    lb._extract_rust_std_source(destination)
                extract.assert_not_called()
                self.assertTrue(destination.exists())

    def test_reextraction_restores_modified_path_crate_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, _library = self.extraction(root / 'original')
            payload = archive / 'rust-src/lib/rustlib/src/rust/library/core/payload.rs'
            payload.write_text('original compiler source')
            blob = root / 'source.tar.xz'
            with tarfile.open(blob, 'w:xz') as tar:
                tar.add(archive, arcname='rust-src-nightly')
            destination = root / 'destination'
            with self.lock(root), mock.patch.object(lb.Cache, 'require', return_value=blob):
                library = lb._extract_rust_std_source(destination)
                (library / 'core/payload.rs').write_text('tampered source')
                library = lb._extract_rust_std_source(destination)
            self.assertEqual((library / 'core/payload.rs').read_text(),
                             'original compiler source')

    def test_environment_receipt_and_variables_share_the_verified_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / 'destination'
            _archive, library = self.extraction(destination)
            with self.lock(root), mock.patch.object(lb, '_extract_rust_std_source',
                    return_value=library):
                env = lb._rust_std_source_environment(destination)
            receipt = json.loads(Path(env['PYTHON_BUILD_RUST_STD_INPUT_RECEIPT']).read_text())
            self.assertEqual(receipt['library'], env['PYTHON_BUILD_RUST_STD_SOURCE'])
            self.assertEqual(receipt['compiler_revision'],
                             env['PYTHON_BUILD_RUST_STD_REVISION'])
            self.assertEqual(receipt['library_cargo_lock_sha256'],
                             env['PYTHON_BUILD_RUST_STD_LOCK_SHA256'])
            self.assertEqual(receipt['input']['name'], 'rust-std-src')
            self.assertEqual(receipt['input']['sha256'], self.std_entry['sha256'])

    def test_committed_notices_and_upstream_lock_match_their_integrity_pins(self):
        route = Path(__file__).resolve().parents[1] / 'overlay/Modules/_csv_rs/std_source'
        index = json.loads((route / 'NOTICES.json').read_text())
        self.assertEqual(len(index['notices']), 41)
        self.assertEqual(hashlib.sha256((route / 'Cargo.lock').read_bytes()).hexdigest(),
                         '75848db58a70444bfb62c649b103d19c5d92fede325eb0c8c0e5442848448669')
        for notice in index['notices']:
            with self.subTest(owner=notice['owner'], file=notice['notice_file']):
                self.assertEqual(hashlib.sha256((route / notice['notice_file']).read_bytes())
                                 .hexdigest(), notice['notice_sha256'])

    def test_extracted_revision_version_and_library_lock_are_checked(self):
        for field in ('git-commit-hash', 'version', 'Cargo.lock'):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                archive, library = self.extraction(root / 'extracted')
                path = library / field if field == 'Cargo.lock' else archive / field
                path.write_text('tampered')
                with self.lock(root):
                    with self.assertRaises(lb.LaneError):
                        lb._rust_std_source_root(root / 'extracted')


if __name__ == '__main__':
    unittest.main()
