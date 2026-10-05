import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('csv_source_aggregate', Path(__file__).with_name('csv_source_aggregate.py'))
recipe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recipe)


class SourceAggregate(unittest.TestCase):
    def test_exact_root_is_one_joint_cargo_owner_for_seven_unchanged_dependencies(self):
        args = recipe.consumer_arguments('/cargo', Path('/source'), 2)
        self.assertEqual([args[i + 1] for i, arg in enumerate(args[:-1]) if arg == '--package'], [recipe.PACKAGE])
        self.assertIn('--locked', args)
        self.assertIn('--offline', args)
        self.assertIn('target-applies-to-host=false', args)
        self.assertNotIn('_pathlib_rs', args)

    def test_runtime_uses_original_std_archive_and_full_metadata_not_dynamic_replay(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            def unit(name, dependencies=()):
                output = root / 'std' / name
                output.mkdir(parents=True)
                for suffix in ('rlib', 'rmeta'):
                    (output / ('lib' + name + '-hash.' + suffix)).write_bytes((name + suffix).encode())
                args = ['rustc', '--crate-name', name, '--crate-type', 'rlib', '--target', recipe.TARGET,
                        '--out-dir', str(output), '-C', 'extra-filename=-hash', '-C', 'panic=abort']
                for dependency in dependencies:
                    args += ['--extern', dependency + '=' + str(root / 'std' / dependency / ('lib' + dependency + '-hash.rmeta'))]
                return {'argv': args, 'query': False, 'exit_code': 0, 'reaped_exit': 0}
            core = unit('core')
            alloc = unit('alloc', ('core',))
            std = unit('std', ('core', 'alloc'))
            runtime = recipe.prepare_runtime(root, std, [std, core, alloc])
            self.assertEqual(runtime['pairs']['std'], [str(x) for x in recipe.std.runtime_artifacts(std)])
            self.assertTrue(all(not path.endswith('.dylib') for path in runtime['files']))
            self.assertEqual(len(runtime['files']), 6)
            recipe.std.verify_target_sysroot(root, runtime['target_sysroot'], runtime['pairs'], std, [std, core, alloc])
            with self.assertRaises(FileExistsError):
                recipe.prepare_runtime(root, std, [std, core, alloc])

    def test_root_externs_bind_both_helper_code_and_full_metadata_and_emit_root_metadata(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            args = ['--crate-name', recipe.CRATE, '--crate-type', 'cdylib', '--emit=dep-info,link',
                    '--target', recipe.TARGET, '--sysroot', '/old']
            for name in recipe.CONSUMERS:
                metadata = root / ('lib' + name + '.rmeta')
                metadata.write_bytes(b'full')
                metadata.with_suffix('.rlib').write_bytes(b'code')
                args += ['--extern', name + '=' + str(metadata)]
            pairs = {name: ['/' + name + '.rlib', '/' + name + '.rmeta'] for name in ('std', 'core', 'alloc')}
            actual = recipe.target_arguments(args, pairs, [], '/owned')
            for name in recipe.CONSUMERS:
                self.assertIn(name + '=' + str(root / ('lib' + name + '.rlib')), actual)
                self.assertIn(name + '=' + str(root / ('lib' + name + '.rmeta')), actual)
            self.assertIn('--emit=dep-info,metadata,link', actual)
            with self.assertRaisesRegex(ValueError, 'helper'):
                recipe.target_arguments(args[:-2], pairs, [], '/owned')
            with self.assertRaisesRegex(ValueError, 'dynamic'):
                recipe.target_arguments([*args, '-C', 'prefer-dynamic'], pairs, [], '/owned')

    def test_python_dynamic_lookups_are_only_exact_strong_input_bound_api_definitions(self):
        surface = {'loads': ['/usr/lib/libSystem.B.dylib'], 'exports': {name: 0 for name in recipe.INITS},
                   'imports': [{'symbol': '_malloc', 'ordinal': 1, 'weak': False},
                               {'symbol': '_PyLong_FromLong', 'ordinal': -2, 'weak': False}]}
        native = {'exports': {'_PyLong_FromLong': 0}}
        recipe.verify_binding_surface(surface, native)
        for row in ({'symbol': '_unknown', 'ordinal': -2, 'weak': False},
                    {'symbol': '_PyLong_FromLong', 'ordinal': -2, 'weak': True},
                    {'symbol': '_malloc', 'ordinal': 0, 'weak': False}):
            with self.subTest(row=row), self.assertRaises(ValueError):
                recipe.verify_binding_surface({**surface, 'imports': [row]}, native)
        with self.assertRaises(ValueError):
            recipe.verify_binding_surface({**surface, 'loads': [*surface['loads'], '@rpath/libstd.dylib']}, native)
        with self.assertRaises(ValueError):
            recipe.verify_binding_surface({**surface, 'exports': {**surface['exports'], '_new_api': 0}}, native)

    def test_publication_has_one_canonical_copy_and_only_relative_same_directory_aliases(self):
        with tempfile.TemporaryDirectory() as raw:
            build = Path(raw).resolve()
            release = build / 'target' / recipe.TARGET / 'release' / recipe.BASENAME
            release.parent.mkdir(parents=True)
            release.write_bytes(b'final aggregate')
            receipt = {'aggregate': recipe.std.artifact(release)}
            modules = build / 'Modules'
            modules.mkdir()
            canonical = modules / recipe.BASENAME
            with patch.object(recipe, 'verify_build_receipt', return_value=receipt):
                recipe.publish_consumer(build, build, recipe.TARGET, None, canonical, {}, canonical=True)
                for name in recipe.CONSUMERS:
                    alias = modules / (name + '.cpython-316-darwin.so')
                    recipe.publish_consumer(build, build, recipe.TARGET, name, alias, {})
                    self.assertTrue(alias.is_symlink())
                    self.assertEqual(alias.readlink(), Path(recipe.BASENAME))
                    self.assertEqual(alias.resolve(), canonical)
                recipe.publish_consumer(build, build, recipe.TARGET, '_csv_rs', modules / '_csv_rs.cpython-316-darwin.so', {})
                with self.assertRaises(ValueError):
                    recipe.publish_consumer(build, build, recipe.TARGET, '_pathlib_rs', modules / '_pathlib_rs.so', {})
                canonical.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError, 'canonical'):
                    recipe.publish_consumer(build, build, recipe.TARGET, '_json_rs', modules / '_json_rs.so', {})


if __name__ == '__main__':
    unittest.main()
