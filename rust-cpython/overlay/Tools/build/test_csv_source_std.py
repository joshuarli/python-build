import importlib.util
import os
import io
import hashlib
import json
from pathlib import Path
import tempfile
import tarfile
import unittest

spec = importlib.util.spec_from_file_location('csv_source_std', Path(__file__).with_name('csv_source_std.py'))
recipe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recipe)


class SourceStdArguments(unittest.TestCase):
    def test_target_no_std_uses_code_and_full_metadata_for_all_runtime_crates(self):
        pairs = {'std': ['/provider/libstd.dylib', '/provider/libstd.rmeta'],
                 'core': ['/core/libcore.rlib', '/core/libcore.rmeta'],
                 'alloc': ['/alloc/liballoc.rlib', '/alloc/liballoc.rmeta']}
        original = ['--crate-name', 'memchr', '--target', recipe.TARGET, '--cfg', 'feature="std"']
        actual = recipe.target_arguments(original, pairs, ['/core', '/alloc'])
        self.assertEqual(actual[:len(original)], original)
        for name, paths in pairs.items():
            for path in paths:
                self.assertIn(name + '=' + path, actual)
        self.assertIn('dependency=/provider', actual)

    def test_host_and_target_queries_keep_original_policy(self):
        for original in [['--crate-name', 'build_script_build'],
                         ['--target', recipe.TARGET, '--print=cfg']]:
            self.assertEqual(recipe.target_arguments(original, {}, []), original)

    def test_conflicting_source_runtime_extern_is_not_overridden(self):
        with self.assertRaises(ValueError):
            recipe.target_arguments(['--target', recipe.TARGET, '--extern', 'core=other.rmeta'], {}, [])

    def test_producer_retains_private_full_metadata_and_adds_code_siblings(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            meta = root / 'libcore-abc.rmeta'
            meta.write_bytes(b'full metadata')
            meta.with_suffix('.rlib').write_bytes(b'code and reduced metadata')
            original = ['--crate-type', 'rlib', '--extern', 'priv:core=' + str(meta), '--out-dir', '/old']
            args = recipe.producer_arguments(original, root / 'provider')
            self.assertIn('priv:core=' + str(meta), args)
            self.assertIn('priv:core=' + str(meta.with_suffix('.rlib')), args)
            self.assertEqual(args[args.index('--crate-type') + 1], 'dylib')

    def test_actual_buildscript_environment_is_parsed_without_guesses(self):
        self.assertEqual(recipe.buildscript_environment('cargo:rustc-env=STD_ENV_ARCH=aarch64\ncargo::rustc-env=OTHER=a=b\n'),
                         {'STD_ENV_ARCH': 'aarch64', 'OTHER': 'a=b'})
        with self.assertRaises(ValueError):
            recipe.buildscript_environment('cargo:rustc-env=X=a\ncargo:rustc-env=X=b\n')

    def test_std_selection_rejects_failed_or_duplicate_producers(self):
        good = {'argv': ['rustc', '--crate-name', 'std', '--target', recipe.TARGET],
                'query': False, 'exit_code': 0, 'reaped_exit': 0}
        self.assertEqual(recipe.select_std_unit([good]), good)
        with self.assertRaises(ValueError):
            recipe.select_std_unit([good, good])
        with self.assertRaises(ValueError):
            recipe.select_std_unit([{**good, 'exit_code': 1}])

    def test_closed_jobserver_fd_is_never_forwarded(self):
        read, write = os.pipe()
        try:
            self.assertEqual(recipe.jobserver_fds(f'-j --jobserver-auth={read},{write}'), (read, write))
            os.close(write)
            self.assertEqual(recipe.jobserver_fds(f'--jobserver-fds={read},{write}'), (read,))
        finally:
            os.close(read)

    def test_runtime_closure_excludes_planned_unwind_root_and_rejects_missing_identity(self):
        def unit(name, dependencies=()):
            argv = ['rustc', '--crate-name', name, '--target', recipe.TARGET, '--out-dir', '/' + name]
            for dep in dependencies:
                argv += ['--extern', 'priv:' + dep + '=/' + dep + '/lib' + dep + '.rmeta']
            return {'argv': argv, 'query': False, 'exit_code': 0, 'reaped_exit': 0}
        core, std, extra = unit('core'), unit('std', ['core']), unit('panic_unwind')
        self.assertEqual(recipe.runtime_closure(std, [std, core, extra]), [std, core])
        with self.assertRaisesRegex(ValueError, 'unique compiler receipt'):
            recipe.runtime_closure(std, [std, extra])

    def test_mirror_reuse_requires_same_build_owner_and_final_bytes(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            build = root / 'build'
            build.mkdir()
            provider = build / 'libstd-test.dylib'
            provider.write_bytes(b'signed provider')
            first = recipe.publish_build_mirror(provider, build)
            self.assertEqual(recipe.publish_build_mirror(provider, build), first)
            provider.write_bytes(b'different producer')
            with self.assertRaisesRegex(ValueError, 'collision'):
                recipe.publish_build_mirror(provider, build)
            provider.write_bytes(b'signed provider')
            (root / 'rust-cpython/.csv-source-std-owner.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'different owner'):
                recipe.publish_build_mirror(provider, build)

    def test_vendor_materialization_checks_archive_before_using_package_bytes(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            library = root / 'library'
            library.mkdir()
            cache = root / 'cargo/registry/cache/index'
            cache.mkdir(parents=True)
            archive = cache / 'tiny-1.0.0.crate'
            with tarfile.open(archive, 'w:gz') as stream:
                data = b'[package]\nname="tiny"\nversion="1.0.0"\n'
                member = tarfile.TarInfo('tiny-1.0.0/Cargo.toml')
                member.size = len(data)
                stream.addfile(member, io.BytesIO(data))
            checksum = recipe.digest(archive)
            (library / 'Cargo.lock').write_text('version=4\n[[package]]\nname="tiny"\nversion="1.0.0"\nsource="registry+https://github.com/rust-lang/crates.io-index"\nchecksum="' + checksum + '"\n')
            archives, files = recipe.materialize_vendor(library, root / 'cargo', root / 'vendor')
            self.assertEqual(archives[0]['sha256'], checksum)
            recipe.verify_files(files)
            record = json.loads((root / 'vendor/tiny-1.0.0/.cargo-checksum.json').read_text())
            self.assertEqual(record['package'], checksum)
            archive.write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, 'missing or changed'):
                recipe.materialize_vendor(library, root / 'cargo', root / 'different-vendor')


if __name__ == '__main__':
    unittest.main()
