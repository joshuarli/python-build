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
                    '--target', recipe.TARGET, '--sysroot', '/old', '-C', 'link-arg=-Wl,-dead_strip_dylibs']
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

    def test_compiler_logger_keeps_owned_lifetime_and_verified_probe_bypass(self):
        import ast
        original = Path(recipe.std.__file__).with_name('csv_source_std_rustc.py').read_text()
        changed = recipe.logger_source()
        compile(changed, 'aggregate-logger', 'exec')
        imports = '    from csv_source_aggregate import target_arguments, helper_dependencies, CRATE\n'
        row = ("    if not query and '--crate-name' in args and args[args.index('--crate-name') + 1] == CRATE:\n"
               "        row['aggregate_dependencies'] = helper_dependencies(args)\n")
        self.assertEqual(changed.replace(imports, '').replace(row, ''), original)
        calls = [node for node in ast.walk(ast.parse(changed)) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and node.func.attr == 'Popen']
        self.assertEqual(len(calls), 1)
        self.assertTrue(next(keyword.value.value for keyword in calls[0].keywords if keyword.arg == 'start_new_session'))
        self.assertIn("if config['runtime_pairs'] and not probe and not query:", changed)

    def test_root_inputs_are_exact_successful_rlib_units_not_separate_helper_images(self):
        import copy
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw).resolve()
            pairs = {name: ['/' + name + '.rlib', '/' + name + '.rmeta'] for name in ('std', 'core', 'alloc')}
            rows = []
            original = ['rustc', '--crate-name', recipe.CRATE, '--crate-type', 'cdylib', '--emit=dep-info,link',
                        '--target', recipe.TARGET, '--sysroot', '/original', '--out-dir', str(folder),
                        '-C', 'link-arg=-Wl,-dead_strip_dylibs']
            for name in recipe.CONSUMERS:
                output = folder / name
                output.mkdir()
                for suffix in ('rlib', 'rmeta'):
                    (output / ('lib' + name + '.' + suffix)).write_bytes((name + suffix).encode())
                args = ['rustc', '--crate-name', name, '--crate-type', 'rlib', '--target', recipe.TARGET,
                        '--sysroot', '/owned', '--out-dir', str(output)]
                for runtime, paths in pairs.items():
                    for path in paths:
                        args += ['--extern', runtime + '=' + path]
                rows.append({'argv': args, 'query': False, 'exit_code': 0, 'reaped_exit': 0})
                original += ['--extern', name + '=' + str(output / ('lib' + name + '.rmeta'))]
            actual = ['rustc', *recipe.target_arguments(original[1:], pairs, [], '/owned')]
            root = {'original_argv': original, 'argv': actual, 'query': False, 'exit_code': 0,
                    'reaped_exit': 0, 'aggregate_dependencies': recipe.helper_dependencies(actual)}
            recipe.select_graph([*rows, root], pairs, '/owned', [])
            for defect in ('missing', 'helper-image', 'wrong-input', 'root-arg', 'root-fail'):
                altered, newroot = copy.deepcopy(rows), copy.deepcopy(root)
                if defect == 'missing':
                    altered.pop()
                elif defect == 'helper-image':
                    altered[0]['argv'][altered[0]['argv'].index('--crate-type') + 1] = 'cdylib'
                elif defect == 'wrong-input':
                    newroot['aggregate_dependencies']['_csv_rs'][0]['sha256'] = 'different'
                elif defect == 'root-arg':
                    newroot['argv'] += ['-C', 'prefer-dynamic']
                else:
                    newroot['exit_code'] = 1
                with self.subTest(defect=defect), self.assertRaises(ValueError):
                    recipe.select_graph([*altered, newroot], pairs, '/owned', [])

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

    def test_receipt_rejects_alias_runtime_metadata_and_canonical_owner_changes(self):
        import copy
        with tempfile.TemporaryDirectory() as raw:
            work = Path(raw).resolve()
            source, build = work / 'source', work / 'build'
            source.mkdir(); build.mkdir()
            root = build / 'source-aggregate356'
            root.mkdir()
            def write(path, content):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                return recipe.std.artifact(path)
            def runtime_unit(name, dependencies=()):
                output = root / 'std-target' / name
                for suffix in ('rlib', 'rmeta'):
                    write(output / ('lib' + name + '.' + suffix), (name + suffix).encode())
                argv = ['rustc', '--crate-name', name, '--crate-type', 'rlib', '--target', recipe.TARGET,
                        '--out-dir', str(output)]
                for dependency in dependencies:
                    argv += ['--extern', dependency + '=' + str(root / 'std-target' / dependency / ('lib' + dependency + '.rmeta'))]
                return {'argv': argv, 'query': False, 'exit_code': 0, 'reaped_exit': 0}
            core = runtime_unit('core')
            alloc = runtime_unit('alloc', ('core',))
            std = runtime_unit('std', ('core', 'alloc'))
            runtime_rows = [std, core, alloc]
            runtime = recipe.prepare_runtime(root, std, runtime_rows)
            leaves = []
            root_args = ['rustc', '--crate-name', recipe.CRATE, '--crate-type', 'cdylib', '--emit=dep-info,link',
                         '--target', recipe.TARGET, '--sysroot', '/original',
                         '--out-dir', str(root / 'consumer-target' / 'aggregate'),
                         '-C', 'link-arg=-Wl,-dead_strip_dylibs']
            for name in recipe.CONSUMERS:
                output = root / 'consumer-target' / name
                for suffix in ('rlib', 'rmeta'):
                    write(output / ('lib' + name + '.' + suffix), (name + suffix).encode())
                argv = ['rustc', '--crate-name', name, '--crate-type', 'rlib', '--target', recipe.TARGET,
                        '--out-dir', str(output), '--sysroot', runtime['target_sysroot']['path']]
                for label, pair in runtime['pairs'].items():
                    for path in pair:
                        argv += ['--extern', label + '=' + path]
                leaves.append({'argv': argv, 'query': False, 'exit_code': 0, 'reaped_exit': 0})
                root_args += ['--extern', name + '=' + str(output / ('lib' + name + '.rmeta'))]
            actual = ['rustc', *recipe.target_arguments(root_args[1:], runtime['pairs'], runtime['directories'], runtime['target_sysroot']['path'])]
            unit = {'argv': actual, 'original_argv': root_args, 'query': False, 'exit_code': 0,
                    'reaped_exit': 0, 'aggregate_dependencies': recipe.helper_dependencies(actual)}
            compiler_path = recipe.std.runtime_output_paths(unit)[0].with_suffix('.dylib')
            raw_image = write(compiler_path, b'raw')
            raw_metadata = write(compiler_path.with_suffix('.rmeta'), b'root metadata')
            finalized = write(root / 'final' / recipe.BASENAME, b'signed')
            canonical = write(build / 'target' / recipe.TARGET / 'release' / recipe.BASENAME, b'signed')
            surface = {'loads': ['/usr/lib/libSystem.B.dylib'], 'exports': {name: 0 for name in recipe.INITS},
                       'imports': [], 'install_id': '@rpath/' + recipe.BASENAME}
            layout = {'link_surface': surface}
            aggregate = {**canonical, 'final_artifact': finalized, 'compiler_artifact': raw_image,
                         'metadata': raw_metadata, 'unit_receipt': unit, 'install_id': surface['install_id'],
                         'layout': layout, 'raw_layout': layout, 'mandatory_exports': []}
            consumers = {}
            for name, leaf in zip(recipe.CONSUMERS, leaves):
                alias = Path(canonical['path']).with_name('lib' + name + '.dylib')
                alias.symlink_to(recipe.BASENAME)
                code, metadata = recipe.std.runtime_artifacts(leaf)
                consumers[name] = {'path': str(alias), 'sha256': canonical['sha256'], 'size': canonical['size'],
                                   'rlib': recipe.std.artifact(code), 'metadata': recipe.std.artifact(metadata), 'unit_receipt': leaf}
            native = write(build / 'libpython3.16.dylib', b'input-bound native Python')
            binding = write(root / 'consumer-target/cpython-sys/c_api.rs', b'typed API')
            metadata = {'sha256': 'archive', 'compiler_revision': 'revision', 'library_cargo_lock_sha256': 'lock'}
            receipt = {'schema_version': 1, 'status': 'complete', 'target': recipe.TARGET, 'build': str(build),
                       'profile': 'release', 'panic': 'abort', 'allocator': 'System',
                       'source': {'path': str(source), 'std_archive_sha256': 'archive', 'std_revision': 'revision',
                                  'std_lock_sha256': 'lock', 'input_files': {}},
                       'runtime_pairs': runtime['pairs'], 'runtime_files': runtime['files'],
                       'runtime_directories': runtime['directories'], 'target_sysroot': runtime['target_sysroot'],
                       'aggregate': aggregate, 'native_api': native, 'consumers': consumers,
                       'generated_bindings': [binding], 'units': [*runtime_rows, *leaves, unit]}
            packet = root / 'receipt.json'
            with patch.object(recipe, 'verify_aggregate_layout', return_value=layout), \
                 patch.object(recipe.std, 'macho_link_surface', return_value=surface), \
                 patch.object(recipe.std, 'verify_compiler_units'):
                packet.write_text(json.dumps(receipt))
                self.assertEqual(recipe.verify_build_receipt(source, build, recipe.TARGET, metadata), receipt)
                for defect in ('schema', 'runtime', 'metadata', 'native-owner', 'canonical', 'extra-helper'):
                    altered = copy.deepcopy(receipt)
                    if defect == 'schema':
                        altered['schema_version'] = 8
                    elif defect == 'runtime':
                        altered['runtime_pairs']['std'] = altered['runtime_pairs']['core']
                    elif defect == 'metadata':
                        altered['aggregate']['metadata']['sha256'] = 'wrong'
                    elif defect == 'native-owner':
                        altered['native_api'] = raw_image
                    elif defect == 'canonical':
                        altered['aggregate']['path'] = consumers['_csv_rs']['path']
                    else:
                        altered['consumers']['_pathlib_rs'] = consumers['_csv_rs']
                    packet.write_text(json.dumps(altered))
                    with self.subTest(defect=defect), self.assertRaises(ValueError):
                        recipe.verify_build_receipt(source, build, recipe.TARGET, metadata)

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
