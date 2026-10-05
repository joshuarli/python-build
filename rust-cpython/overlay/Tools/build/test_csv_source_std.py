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
    def test_std_feature_override_is_explicitly_empty_without_changing_abort_or_host_policy(self):
        args = recipe.std_arguments('cargo', Path('/probe'), recipe.TARGET, 2,
                                    'clang', Path('/library'), ['--sysroot', '/view'])
        self.assertIn('-Zbuild-std-features=', args)
        self.assertNotIn('-Zbuild-std-features=backtrace', args)
        self.assertIn('-Zbuild-std=std,panic_abort', args)
        self.assertIn('--locked', args)
        self.assertIn('--offline', args)
        self.assertIn('target-applies-to-host=false', args)
        self.assertIn('host.rustflags=["--sysroot", "/view"]', args)

    def test_actual_std_producer_rejects_symbolization_or_unwind_feature_selection(self):
        good = {'argv': ['rustc', '--crate-name', 'std', '--target', recipe.TARGET],
                'query': False, 'exit_code': 0, 'reaped_exit': 0}
        for cfg in ('feature="backtrace"', 'feature="panic-unwind"',
                    'feature="backtrace-trace-only"'):
            for added in (['--cfg', cfg], ['--cfg=' + cfg]):
                with self.subTest(added=added), self.assertRaisesRegex(ValueError, 'std feature'):
                    recipe.select_std_unit([{**good, 'argv': good['argv'] + added}])
        self.assertEqual(recipe.select_std_unit([good]), good)

    def test_consumer_id_remains_compiler_owned_after_release_bytes_are_normalized(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            output = root / 'target/release/build/_csv_rs/hash/out'
            output.mkdir(parents=True)
            compiled = output / 'lib_csv_rs.dylib'
            compiled.write_bytes(b'original compiler output')
            release = root / 'target/release/lib_csv_rs.dylib'
            release.write_bytes(compiled.read_bytes())
            unit = {'argv': ['rustc', '--crate-name', '_csv_rs', '--crate-type', 'cdylib',
                             '--out-dir', str(output)]}
            raw_record = recipe.artifact(compiled)
            self.assertEqual(recipe.consumer_install_id(unit, release, root), str(compiled))
            release.write_bytes(b'normalized and signed release')
            self.assertEqual(recipe.consumer_install_id(unit, release, root), str(compiled))
            self.assertEqual(recipe.artifact(compiled), raw_record)
            self.assertNotEqual(recipe.artifact(release)['sha256'], raw_record['sha256'])


    def test_consumer_self_id_is_verified_separately_from_its_actual_dependencies(self):
        own = '/owned/target/release/build/_csv_rs/hash/out/lib_csv_rs.dylib'
        provider = '@rpath/libstd-hash.dylib'
        loads = 'lib_csv_rs.dylib:\n\t' + own + ' (compatibility version 0.0.0)\n\t' + provider + ' (compatibility version 0.0.0)\n\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0)\n'
        commands = ('Load command 0\n cmd LC_ID_DYLIB\n cmdsize 80\n name ' + own + ' (offset 24)\n'
                    'Load command 1\n cmd LC_LOAD_DYLIB\n cmdsize 80\n name ' + provider + ' (offset 24)\n'
                    'Load command 2\n cmd LC_LOAD_DYLIB\n cmdsize 80\n name /usr/lib/libSystem.B.dylib (offset 24)\n')
        self.assertEqual(recipe.runtime_dependencies(loads, commands, own, provider),
                         [provider, '/usr/lib/libSystem.B.dylib'])
        with self.assertRaisesRegex(ValueError, 'install identity'):
            recipe.runtime_dependencies(loads, commands.replace('LC_ID_DYLIB', 'LC_LOAD_DYLIB'), own, provider)
        with self.assertRaisesRegex(ValueError, 'install identity'):
            recipe.runtime_dependencies(loads, commands, '/foreign/lib_csv_rs.dylib', provider)
        foreign = commands + 'Load command 3\n cmd LC_LOAD_DYLIB\n cmdsize 80\n name /owned/libother.dylib (offset 24)\n'
        foreign_loads = loads + '\t/owned/libother.dylib (compatibility version 0.0.0)\n'
        with self.assertRaisesRegex(ValueError, 'non-system'):
            recipe.runtime_dependencies(foreign_loads, foreign, own, provider)


    def test_verified_host_capability_probe_preserves_original_args_and_failure_receipt(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            package = root / 'proc-macro2-1.0.107'
            source = package / 'src/probe/proc_macro_span.rs'
            source.parent.mkdir(parents=True)
            source.write_text('extern crate proc_macro;')
            (package / 'build.rs').write_text('verified build script')
            (package / 'Cargo.toml').write_text('[package]\nname="proc-macro2"\nversion="1.0.107"\n')
            target = root / 'target'
            output = target / 'release/build/proc-macro2/abc/out'
            output.mkdir(parents=True)
            args = ['--cfg=procmacro2_build_probe', '--edition=2021', '--crate-name=proc_macro2',
                    '--crate-type=lib', '--cap-lints=allow', '--emit=dep-info,metadata',
                    '--out-dir', str(output / 'probe'), 'src/probe/proc_macro_span.rs', '--target', recipe.TARGET]
            environment = {'CARGO_PKG_NAME': 'proc-macro2', 'CARGO_PKG_VERSION': '1.0.107',
                           'CARGO_MANIFEST_DIR': str(package), 'HOST': recipe.TARGET, 'TARGET': recipe.TARGET,
                           'OUT_DIR': str(output), 'RUSTC': str(root / 'rustc-logger.py')}
            files = {str(p): recipe.digest(p) for p in package.rglob('*') if p.is_file()}
            self.assertTrue(recipe.host_capability_probe(args, environment, str(package), files, target))
            row = {'original_argv': ['rustc', *args], 'argv': ['rustc', *args], 'environment': environment,
                   'cwd': str(package), 'query': False, 'exit_code': 1, 'reaped_exit': 1,
                   'source_files': {str(source): recipe.digest(source)}}
            recipe.verify_compiler_units([row], files, target)
            with self.assertRaisesRegex(ValueError, 'probe arguments changed'):
                recipe.verify_compiler_units([{**row, 'argv': [*row['argv'], '--extern', 'std=other.rmeta']}], files, target)
            with self.assertRaisesRegex(ValueError, 'failed compiler unit'):
                recipe.verify_compiler_units([{**row, 'original_argv': ['rustc', '--crate-name', 'real']}], files, target)
            with self.assertRaises(ValueError):
                recipe.host_capability_probe(args, {**environment, 'OUT_DIR': str(root / 'foreign')}, str(package), files, target)

    def test_runtime_alias_resolves_by_exact_metadata_artifact_not_extern_label(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            def unit(name, suffix):
                for extension in ('.rmeta', '.rlib'):
                    (root / ('lib' + name + suffix + extension)).write_bytes(b'unit artifact')
                return {'argv': ['rustc', '--crate-name', name, '--target', recipe.TARGET,
                                 '--out-dir', str(root), '-C', 'extra-filename=' + suffix],
                        'query': False, 'exit_code': 0, 'reaped_exit': 0}
            shim = unit('rustc_std_workspace_core', '-7038bf0a')
            std = unit('std', '-producer')
            probe = {'argv': ['rustc', '--crate-name', 'probe', '--target', recipe.TARGET,
                              '--out-dir', str(root), '--crate-type', 'cdylib'],
                     'query': False, 'exit_code': 0, 'reaped_exit': 0}
            metadata = root / 'librustc_std_workspace_core-7038bf0a.rmeta'
            std['argv'] += ['--extern', 'priv:core=' + str(metadata)]
            self.assertEqual(recipe.runtime_closure(std, [std, shim, probe]), [std, shim])
            with self.assertRaisesRegex(ValueError, 'unique compiler receipt'):
                recipe.runtime_closure(std, [std])
            with self.assertRaisesRegex(ValueError, 'unique compiler receipt'):
                recipe.runtime_closure(std, [std, shim, dict(shim)])


    def test_native_prerequisite_ignores_neighbor_rust_helper_and_rejects_missing_or_duplicate(self):
        with tempfile.TemporaryDirectory() as raw:
            modules = Path(raw).resolve()
            native = modules / '_struct.cpython-316-darwin.so'
            native.write_bytes(b'native prerequisite')
            (modules / '_struct_rs.cpython-316-darwin.so').write_bytes(b'Rust helper')
            self.assertEqual(recipe.native_prerequisite(modules, '_struct'), native)
            (modules / '_struct.other.so').write_bytes(b'duplicate native')
            with self.assertRaisesRegex(ValueError, 'ambiguous'):
                recipe.native_prerequisite(modules, '_struct')
            native.unlink()
            (modules / '_struct.other.so').unlink()
            with self.assertRaisesRegex(ValueError, 'missing'):
                recipe.native_prerequisite(modules, '_struct')

    def test_joint_normalization_proves_each_self_id_and_keeps_raw_compiler_images(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            provider = root / 'provider/libstd-test.dylib'
            provider.parent.mkdir()
            provider.write_bytes(b'std')
            consumers, units, originals = {}, {}, {}
            for name in recipe.CONSUMERS:
                output = root / 'consumer-target/release/build' / name / 'hash/out'
                output.mkdir(parents=True)
                compiled = output / ('lib' + name + '.dylib')
                compiled.write_bytes(name.encode())
                release = root / 'consumer-target/release' / compiled.name
                release.write_bytes(compiled.read_bytes())
                consumers[name] = release
                units[name] = {'argv': ['rustc', '--crate-name', name, '--crate-type', 'cdylib', '--out-dir', str(output)]}
                originals[name] = recipe.artifact(compiled)
            calls, provider_loads = [], {str(path): str(provider) for path in consumers.values()}
            def run(argv, cwd, environment, log, commands, timeout=180):
                calls.append(argv)
                image = Path(argv[-1])
                if argv[0] == '/usr/bin/install_name_tool':
                    if argv[1] == '-change':
                        provider_loads[str(image)] = argv[3]
                    return ''
                if argv[0] == '/usr/bin/codesign':
                    if argv[1] == '--force':
                        image.write_bytes(image.read_bytes() + b' signed')
                    return ''
                own = '@rpath/' + provider.name if image == provider else str(Path(originals[next(n for n,p in consumers.items() if p == image)]['path']))
                loads = ['/usr/lib/libSystem.B.dylib'] if image == provider else [provider_loads[str(image)], '/usr/lib/libSystem.B.dylib']
                if argv[1] == '-L':
                    return str(image) + ':\n' + ''.join('\t' + value + ' (compatibility version 0.0.0)\n' for value in [own, *loads])
                result = 'Load command 0\n cmd LC_ID_DYLIB\n name ' + own + ' (offset 24)\n'
                for i, value in enumerate(loads, 1):
                    result += 'Load command ' + str(i) + '\n cmd LC_LOAD_DYLIB\n name ' + value + ' (offset 24)\n'
                if image != provider:
                    result += 'Load command 3\n cmd LC_RPATH\n cmdsize 64\n path @loader_path/../../rust-cpython (offset 12)\n'
                return result
            with patch.object(recipe, 'run', side_effect=run):
                install_id, rpath, dependencies = recipe.normalized_outputs(provider, consumers, {}, [], root, units)
            self.assertEqual(install_id, '@rpath/libstd-test.dylib')
            self.assertEqual(rpath, '@loader_path/../../rust-cpython')
            self.assertEqual(sum(call[:2] == ['/usr/bin/codesign', '--force'] and call[-1] == provider for call in calls), 1)
            for name, path in consumers.items():
                self.assertEqual(dependencies[name], [install_id, '/usr/lib/libSystem.B.dylib'])
                self.assertEqual(recipe.artifact(originals[name]['path']), originals[name])
                self.assertNotEqual(recipe.digest(path), originals[name]['sha256'])

    def test_source_closure_includes_five_helpers_without_neighbor_source(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            source, build, library = root / 'source', root / 'build', root / 'library'
            def write(path):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'owned source')
                return path
            selected = ('_csv_rs', '_json_rs', '_pathlib_rs', '_typing_rs', '_tokenize_rs')
            helper_sources = [write(source / 'Modules' / name / 'src/lib.rs') for name in selected]
            neighbor = write(source / 'Modules/_socket_rs/src/lib.rs')
            for relative in ('Cargo.toml', 'Cargo.lock', 'Python/stdlib_module_names.h',
                             'Modules/cpython-sys/src/lib.rs', 'Modules/cpython-build-helper/src/lib.rs',
                             'Include/Python.h'):
                write(source / relative)
            for relative in ('Makefile', 'pyconfig.h', 'libpython3.16.dylib'):
                write(build / relative)
            for name in ('_posixsubprocess', 'math', 'select', '_struct', '_sha2', 'zlib', 'fcntl'):
                write(build / 'Modules' / (name + '.cpython-316-darwin.so'))
            write(library / 'std/src/lib.rs')
            compiler = {'rustc_path': str(write(root / 'rustc')), 'cargo_path': str(write(root / 'cargo'))}
            files = recipe.input_files(source, build, library, compiler)
            for path in helper_sources:
                self.assertEqual(files[str(path)], recipe.digest(path))
            self.assertNotIn(str(neighbor), files)

    def test_joint_consumer_arguments_select_exact_packages_once(self):
        args = recipe.consumer_arguments('cargo', Path('/source'), 2)
        self.assertEqual([args[i + 1] for i, arg in enumerate(args[:-1]) if arg == '--package'],
                         ['_csv_rs', '_json_rs', '_pathlib_rs', '_typing_rs', '_tokenize_rs'])
        self.assertIn('--locked', args)
        self.assertIn('--offline', args)
        self.assertIn('target-applies-to-host=false', args)

    def test_joint_output_units_require_each_consumer_and_same_runtime_pairs(self):
        pairs = {name: ['/' + name + '.code', '/' + name + '.rmeta'] for name in ('std', 'core', 'alloc')}
        def unit(name):
            argv = ['rustc', '--crate-name', name, '--target', recipe.TARGET]
            for label, pair in pairs.items():
                for raw in pair:
                    argv += ['--extern', label + '=' + raw]
            return {'argv': argv, 'query': False, 'exit_code': 0, 'reaped_exit': 0}
        names = ('_csv_rs', '_json_rs', '_pathlib_rs', '_typing_rs', '_tokenize_rs')
        units = [unit(name) for name in names]
        self.assertEqual(set(recipe.consumer_units(units, pairs)), set(names))
        for index in range(len(units)):
            missing = units[:index] + units[index + 1:]
            duplicate = units + [units[index]]
            failed = [*units[:index], {**units[index], 'exit_code': 1}, *units[index + 1:]]
            wrong_pair = [*units[:index], {**units[index], 'argv': units[index]['argv'][:-2]}, *units[index + 1:]]
            for rows in (missing, duplicate, failed, wrong_pair):
                with self.subTest(consumer=names[index]), self.assertRaises(ValueError):
                    recipe.consumer_units(rows, pairs)

    def test_publication_checks_receipt_before_copy_and_keeps_signed_source(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            build, source = root / 'build', root / 'source'
            (build / 'Modules').mkdir(parents=True)
            source.mkdir()
            published = build / 'target' / recipe.TARGET / 'release/lib_pathlib_rs.dylib'
            published.parent.mkdir(parents=True)
            published.write_bytes(b'signed pathlib')
            record = recipe.artifact(published)
            receipt = {'consumers': {'_pathlib_rs': record}}
            output = build / 'Modules/_pathlib_rs.cpython-316-darwin.so'
            with patch.object(recipe, 'verify_build_receipt', return_value=receipt) as verify:
                recipe.publish_consumer(source, build, recipe.TARGET, '_pathlib_rs', output, {})
                verify.assert_called_once()
                self.assertEqual(output.read_bytes(), b'signed pathlib')
                self.assertEqual(published.read_bytes(), b'signed pathlib')
                with self.assertRaises(ValueError):
                    recipe.publish_consumer(source, build, recipe.TARGET, '_pickle_rs', output, {})
                with self.assertRaises(ValueError):
                    recipe.publish_consumer(source, build, recipe.TARGET, '_pathlib_rs', root / output.name, {})
            output.unlink()
            with patch.object(recipe, 'verify_build_receipt', side_effect=ValueError('changed pathlib')):
                with self.assertRaises(ValueError):
                    recipe.publish_consumer(source, build, recipe.TARGET, '_pathlib_rs', output, {})
            self.assertFalse(output.exists())

    def test_completed_joint_receipt_rejects_missing_json_source_runtime_or_final_bytes(self):
        with tempfile.TemporaryDirectory() as raw:
            work = Path(raw).resolve()
            source, build = work / 'source', work / 'build'
            root = build / 'source-std338'
            root.mkdir(parents=True)
            def write(path, data):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                return recipe.artifact(path)
            provider = write(root / 'provider/libstd-test.dylib', b'provider')
            mirror = write(work / 'rust-cpython/libstd-test.dylib', b'provider')
            (work / 'rust-cpython/.csv-source-std-owner.json').write_text(json.dumps({'build': str(build)}))
            pairs = {}
            runtime_files = {}
            for name in ('std', 'core', 'alloc'):
                pair = []
                for suffix in ('code', 'rmeta'):
                    record = write(root / (name + '.' + suffix), b'runtime')
                    pair.append(record['path'])
                    runtime_files[record['path']] = record['sha256']
                pairs[name] = pair
            rows, records = [], {}
            for name in recipe.CONSUMERS:
                record = write(build / 'target' / recipe.TARGET / ('release/lib' + name + '.dylib'), name.encode())
                final = write(root / 'consumer-target' / recipe.TARGET / ('release/lib' + name + '.dylib'), name.encode())
                compiled = write(root / 'consumer-target' / recipe.TARGET / ('release/build/' + name + '/hash/out/lib' + name + '.dylib'), name.encode())
                owned_source = write(source / 'Modules' / name / 'src/lib.rs', b'original helper')
                argv = ['rustc', '--crate-name', name, '--target', recipe.TARGET, '--crate-type', 'cdylib',
                        '--out-dir', str(Path(compiled['path']).parent)]
                for label, pair in pairs.items():
                    for path in pair:
                        argv += ['--extern', label + '=' + path]
                unit = {'argv': argv, 'original_argv': argv, 'environment': {}, 'cwd': str(source),
                        'query': False, 'exit_code': 0, 'reaped_exit': 0, 'source_files': {}}
                rows.append(unit)
                records[name] = {**record, 'artifact_path': final['path'], 'artifact_sha256': final['sha256'],
                                 'compiler_artifact': compiled, 'install_id': compiled['path'], 'raw_artifact': compiled,
                                 'source': owned_source, 'unit_receipt': unit,
                                 'provider_install_id': '@rpath/libstd-test.dylib', 'rpath': '@loader_path/../../rust-cpython'}
            binding = write(root / 'c_api.rs', b'configured C API')
            metadata = {'sha256': 'archive', 'compiler_revision': 'compiler', 'library_cargo_lock_sha256': 'lock'}
            receipt = {'schema_version': 4, 'status': 'complete', 'target': recipe.TARGET, 'build': str(build),
                       'profile': 'release', 'panic': 'abort', 'allocator': 'System',
                       'source': {'path': str(source), 'std_archive_sha256': 'archive', 'std_revision': 'compiler',
                                  'std_lock_sha256': 'lock', 'input_files': {}},
                       'runtime_files': runtime_files, 'runtime_pairs': pairs, 'units': rows,
                       'provider': {**provider, 'install_id': '@rpath/libstd-test.dylib',
                                    'build_mirror_path': mirror['path'], 'build_mirror_sha256': mirror['sha256']},
                       'consumers': records, 'generated_bindings': [binding]}
            path = root / 'receipt.json'
            path.write_text(json.dumps(receipt))
            self.assertEqual(recipe.verify_build_receipt(source, build, recipe.TARGET, metadata), receipt)
            import copy
            for kind in ('missing-json', 'missing-pathlib', 'missing-typing', 'missing-tokenize', 'old-schema', 'old-three-schema', 'wrong-provider', 'missing-pair', 'wrong-unit'):
                altered = copy.deepcopy(receipt)
                if kind == 'missing-json':
                    del altered['consumers']['_json_rs']
                elif kind == 'missing-pathlib':
                    del altered['consumers']['_pathlib_rs']
                elif kind == 'missing-typing':
                    del altered['consumers']['_typing_rs']
                elif kind == 'missing-tokenize':
                    del altered['consumers']['_tokenize_rs']
                elif kind == 'old-three-schema':
                    altered['schema_version'] = 3
                elif kind == 'old-schema':
                    altered['schema_version'] = 2
                elif kind == 'wrong-provider':
                    altered['consumers']['_json_rs']['provider_install_id'] = '@rpath/other.dylib'
                elif kind == 'missing-pair':
                    altered['units'][1]['argv'] = altered['units'][1]['argv'][:-2]
                else:
                    altered['consumers']['_json_rs']['unit_receipt'] = altered['units'][0]
                path.write_text(json.dumps(altered))
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    recipe.verify_build_receipt(source, build, recipe.TARGET, metadata)
            path.write_text(json.dumps(receipt))
            final = Path(records['_json_rs']['artifact_path'])
            final.write_bytes(b'changed JSON')
            with self.assertRaisesRegex(ValueError, 'final release artifact'):
                recipe.verify_build_receipt(source, build, recipe.TARGET, metadata)

    def test_fresh_recipe_rejects_old_selected_publication_without_deleting_it(self):
        with tempfile.TemporaryDirectory() as raw:
            build = Path(raw).resolve()
            recipe.check_fresh_consumer_outputs(build, recipe.TARGET)
            for path in (build / 'Modules/_pathlib_rs.cpython-316-darwin.so',
                         build / 'target' / recipe.TARGET / 'release/lib_pathlib_rs.dylib',
                         build / 'target' / recipe.TARGET / 'release/lib_csv_rs.dylib'):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'old artifact')
                with self.assertRaisesRegex(ValueError, 'pre-existing consumer'):
                    recipe.check_fresh_consumer_outputs(build, recipe.TARGET)
                self.assertEqual(path.read_bytes(), b'old artifact')
                path.unlink()

    def test_bootstrap_imports_owned_modules_without_changing_controller_imports(self):
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location('csv_bootstrap', Path(__file__).with_name('csv_source_std_bootstrap.py'))
        bootstrap = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bootstrap)
        with tempfile.TemporaryDirectory() as raw:
            build = Path(raw).resolve()
            modules = build / 'Modules'
            modules.mkdir()
            (modules / 'csv_bootstrap_marker.py').write_text('OWNER = "configured build"\n')
            interpreter = build / 'python'
            interpreter.write_bytes(b'owned interpreter')
            import sys
            original = list(sys.path)
            try:
                with self.assertRaises(ModuleNotFoundError):
                    __import__('csv_bootstrap_marker')
                with patch.dict(os.environ, {'PYTHON_BUILD_DIR': str(build)}), \
                     patch.object(sys, 'executable', str(interpreter)):
                    self.assertEqual(bootstrap.configure_bootstrap_path(), str(modules))
                    marker = __import__('csv_bootstrap_marker')
                    self.assertEqual(marker.OWNER, 'configured build')
                sys.path[:] = original
                with patch.dict(os.environ, {'PYTHON_BUILD_DIR': str(build)}):
                    with self.assertRaisesRegex(ValueError, 'interpreter'):
                        bootstrap.configure_bootstrap_path()
                self.assertEqual(sys.path, original)
            finally:
                sys.path[:] = original
                sys.modules.pop('csv_bootstrap_marker', None)

    def test_both_cli_preludes_configure_modules_before_heavy_imports(self):
        import ast
        import sys
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location('csv_bootstrap', Path(__file__).with_name('csv_source_std_bootstrap.py'))
        bootstrap = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bootstrap)
        with tempfile.TemporaryDirectory() as raw:
            build = Path(raw).resolve()
            (build / 'Modules').mkdir()
            interpreter = build / 'python'
            interpreter.write_bytes(b'owned interpreter')
            for name in ('csv_source_std.py', 'csv_source_std_rustc.py'):
                nodes = []
                for node in ast.parse(Path(__file__).with_name(name).read_text()).body:
                    if isinstance(node, ast.Import) and any(a.name not in ('os', 'sys') for a in node.names):
                        break
                    nodes.append(node)
                prelude = compile(ast.Module(body=nodes, type_ignores=[]), name, 'exec')
                original = list(sys.path)
                try:
                    with patch.dict(os.environ, {'PYTHON_BUILD_DIR': str(build)}), \
                         patch.dict(sys.modules, {'csv_source_std_bootstrap': bootstrap}), \
                         patch.object(sys, 'executable', str(interpreter)):
                        exec(prelude, {'__name__': 'controller_import'})
                        self.assertEqual(sys.path, original)
                        exec(prelude, {'__name__': '__main__'})
                        self.assertEqual(sys.path[0], str(build / 'Modules'))
                finally:
                    sys.path[:] = original

    def test_build_loader_path_never_accepts_external_or_multiple_runtime_owners(self):
        spec = importlib.util.spec_from_file_location('csv_bootstrap', Path(__file__).with_name('csv_source_std_bootstrap.py'))
        bootstrap = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bootstrap)
        with tempfile.TemporaryDirectory() as raw:
            build = Path(raw).resolve()
            self.assertEqual(bootstrap.build_library_path(build, {}), str(build))
            self.assertEqual(bootstrap.build_library_path(build, {'DYLD_LIBRARY_PATH': str(build)}), str(build))
            for value in ('/foreign', str(build) + ':/foreign'):
                with self.assertRaisesRegex(ValueError, 'library owner'):
                    bootstrap.build_library_path(build, {'DYLD_LIBRARY_PATH': value})

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

    def test_archive_vendor_checksum_validation_preserves_inputs_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as raw:
            library = Path(raw).resolve()
            package = library / 'vendor/tiny-1.0.0'
            package.mkdir(parents=True)
            source = package / 'lib.rs'
            source.write_bytes(b'pub fn value() {}')
            checksum = 'a' * 64
            (library / 'Cargo.lock').write_text('version=4\n[[package]]\nname="tiny"\nversion="1.0.0"\nsource="registry+https://github.com/rust-lang/crates.io-index"\nchecksum="' + checksum + '"\n')
            (package / '.cargo-checksum.json').write_text(json.dumps({'package': checksum, 'files': {'lib.rs': recipe.digest(source)}}))
            before = {str(p): recipe.digest(p) for p in library.rglob('*') if p.is_file()}
            records, files = recipe.validate_vendor(library)
            self.assertEqual(records[0]['checksum'], checksum)
            recipe.verify_files(files)
            self.assertEqual(before, {str(p): recipe.digest(p) for p in library.rglob('*') if p.is_file()})
            source.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'vendor file changed'):
                recipe.validate_vendor(library)

    def test_runtime_output_selection_uses_exact_identity_in_shared_directory(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            for name in ('core-a', 'alloc-b', 'std-c'):
                (root / ('lib' + name + '.rlib')).write_bytes(b'code')
                (root / ('lib' + name + '.rmeta')).write_bytes(b'metadata')
            unit = {'argv': ['rustc', '--crate-name', 'core', '-C', 'extra-filename=-a', '--out-dir', str(root)]}
            code, full = recipe.runtime_artifacts(unit)
            self.assertEqual(code.name, 'libcore-a.rlib')
            self.assertEqual(full.name, 'libcore-a.rmeta')

    def test_initial_receipt_failure_still_kills_and_reaps_compiler(self):
        from unittest.mock import patch, Mock
        spec = importlib.util.spec_from_file_location('csv_logger', Path(__file__).with_name('csv_source_std_rustc.py'))
        logger = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(logger)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            compiler = root / 'rustc'
            compiler.write_bytes(b'compiler')
            config = root / 'config.json'
            config.write_text(json.dumps({'rustc': str(compiler), 'rustc_sha256': recipe.digest(compiler),
                                         'target_directory': str(root), 'source_files': {}, 'runtime_pairs': None,
                                         'receipts': str(root / 'receipts')}))
            process = Mock(pid=123456)
            process.poll.return_value = None
            process.wait.return_value = -9
            with patch.dict(os.environ, {'CSV_SOURCE_STD_RUSTC_CONFIG': str(config)}), \
                 patch.object(logger.sys, 'argv', ['logger', '-vV']), \
                 patch.object(logger.subprocess, 'Popen', return_value=process), \
                 patch.object(logger.os, 'getpgid', return_value=123456), \
                 patch.object(logger.os, 'killpg') as kill, \
                 patch.object(Path, 'write_text', side_effect=OSError('receipt unavailable')):
                with self.assertRaises(OSError):
                    logger.main()
                kill.assert_called_once_with(123456, logger.signal.SIGKILL)
                process.wait.assert_called_once()

    def test_malformed_receipt_does_not_prevent_later_compiler_cleanup(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            receipts = root / 'std-units'
            receipts.mkdir()
            (receipts / '000.json').write_text('{partial')
            (receipts / '001.json').write_text(json.dumps({'state': 'running', 'pid': 123456, 'pgid': 123456}))
            with patch.object(recipe.os, 'killpg') as kill:
                with self.assertRaises(RuntimeError) as failure:
                    recipe.cleanup_compilers(root)
                kill.assert_called_once_with(123456, recipe.signal.SIGKILL)
                self.assertIn('000.json', str(failure.exception))

    def test_failed_atomic_publication_keeps_previous_running_receipt_visible(self):
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location('csv_logger', Path(__file__).with_name('csv_source_std_rustc.py'))
        logger = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(logger)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            receipts = root / 'std-units'
            receipts.mkdir()
            path = receipts / 'unit.json'
            original = {'state': 'running', 'pid': 123456, 'pgid': 123456}
            logger.publish_receipt(path, original)
            with patch.object(logger.os, 'replace', side_effect=OSError('publication failed')):
                with self.assertRaises(OSError):
                    logger.publish_receipt(path, {**original, 'state': 'reaped'})
            self.assertEqual(json.loads(path.read_text()), original)
            with patch.object(recipe.os, 'killpg') as kill:
                report = recipe.cleanup_compilers(root)
                kill.assert_called_once_with(123456, recipe.signal.SIGKILL)
                self.assertEqual(report['faults'], [])



if __name__ == '__main__':
    unittest.main()
