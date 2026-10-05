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
        from unittest.mock import patch
        # This fixture isolates the pre-existing joint publication/unit guards;
        # export-policy replay and raw-byte correspondence are checked separately.
        export_guard = patch.object(recipe, 'verify_export_policy')
        export_guard.start()
        self.addCleanup(export_guard.stop)
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




class SourceStdExportClosure(unittest.TestCase):
    def provider(self):
        exports = {name: 0 for name in recipe.EXPORT_SAFETY_ROOTS}
        exports.update({'__RNvneeded': 0, '__RNvunused': 0, '_rust_metadata_std_0123456789abcdef': 0,
                        **{'__RNvCsTest_7___rustc' + str(len(n)) + '_' + n: 0 for n in recipe.ALLOCATOR_EXPORT_ROOTS},
                        '___isOSVersionAtLeast': 4, '___isPlatformVersionAtLeast': 4})
        return {'install_id': '/owned/full/libstd-hash.dylib',
                'loads': ['/usr/lib/libSystem.B.dylib'], 'exports': exports,
                'imports': [{'ordinal': 1, 'weak': False, 'symbol': '_malloc', 'addend': 0}]}

    def consumers(self):
        result = {name: {'loads': ['/owned/full/libstd-hash.dylib'], 'imports': []}
                  for name in recipe.CONSUMERS}
        result['_csv_rs']['imports'] = [{'ordinal': 1, 'weak': False, 'symbol': '__RNvneeded', 'addend': 0}]
        return result

    def test_export_closure_uses_exact_provider_ordinal_and_accepts_empty_consumer(self):
        consumers = self.consumers()
        consumers['_json_rs']['loads'].append('/usr/lib/libSystem.B.dylib')
        consumers['_json_rs']['imports'].append({'ordinal': 2, 'weak': False, 'symbol': '__RNvunused', 'addend': 0})
        closure = recipe.provider_export_closure(self.provider(), consumers)
        self.assertIn('__RNvneeded', closure['symbols'])
        self.assertNotIn('__RNvunused', closure['symbols'])
        self.assertEqual(closure['consumer_imports']['_typing_rs'], [])
        self.assertTrue(set(recipe.EXPORT_SAFETY_ROOTS) <= set(closure['symbols']))
        self.assertIn('___isOSVersionAtLeast', closure['symbols'])

    def test_missing_consumer_or_provider_symbol_fails_instead_of_flat_union_fallback(self):
        consumers = self.consumers()
        del consumers['_typing_rs']
        with self.assertRaisesRegex(ValueError, 'roster'):
            recipe.provider_export_closure(self.provider(), consumers)
        consumers = self.consumers()
        consumers['_csv_rs']['imports'][0]['symbol'] = '_missing'
        with self.assertRaisesRegex(ValueError, 'definition'):
            recipe.provider_export_closure(self.provider(), consumers)

    def test_weak_self_and_flat_lookup_bindings_are_rejected(self):
        for ordinal in (0, -1, -2, -3, 2):
            provider = self.provider()
            provider['imports'][0]['ordinal'] = ordinal
            with self.assertRaisesRegex(ValueError, 'provider import'):
                recipe.provider_export_closure(provider, self.consumers())
        consumers = self.consumers()
        consumers['_csv_rs']['imports'][0]['weak'] = True
        with self.assertRaisesRegex(ValueError, 'weak'):
            recipe.provider_export_closure(self.provider(), consumers)

    def test_provider_weak_definition_and_allocator_roots_are_exact(self):
        for symbol in (*recipe.EXPORT_SAFETY_ROOTS, '___isOSVersionAtLeast'):
            provider = self.provider()
            del provider['exports'][symbol]
            with self.assertRaisesRegex(ValueError, 'safety root'):
                recipe.provider_export_closure(provider, self.consumers())
        provider = self.provider()
        provider['exports']['_new_weak'] = 4
        with self.assertRaisesRegex(ValueError, 'weak definition'):
            recipe.provider_export_closure(provider, self.consumers())

    def test_restricted_metadata_changes_and_missing_or_extra_exports_fail(self):
        full = self.provider()
        closure = recipe.provider_export_closure(full, self.consumers())
        restricted = {**full, 'exports': {s: full['exports'][s] for s in closure['symbols']}}
        recipe.verify_restricted_provider(full, restricted, closure, 'same', 'same')
        with self.assertRaisesRegex(ValueError, 'metadata'):
            recipe.verify_restricted_provider(full, restricted, closure, 'first', 'second')
        for symbol in ('__RNvneeded', '__RNvunused'):
            changed = {**restricted, 'exports': dict(restricted['exports'])}
            if symbol in changed['exports']:
                del changed['exports'][symbol]
            else:
                changed['exports'][symbol] = 0
            with self.assertRaisesRegex(ValueError, 'export'):
                recipe.verify_restricted_provider(full, changed, closure, 'same', 'same')

    def test_restricted_replay_preserves_all_original_arguments_except_output_and_link_list(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            code = root / 'libcore.rlib'
            code.write_bytes(b'code')
            original = ['rustc', '--crate-type', 'rlib', '--out-dir', '/old',
                        '--extern', 'priv:core=' + str(code.with_suffix('.rmeta')),
                        '-C', 'metadata=identity', '--emit=dep-info,metadata,link']
            full = recipe.producer_arguments(original, root / 'full')
            restricted = recipe.restricted_producer_arguments(original, root / 'provider', root / 'exports.txt')
            self.assertEqual(restricted[:-2], recipe.producer_arguments(original, root / 'provider'))
            self.assertEqual(restricted[-2:], ['-C', 'link-arg=-Wl,-exported_symbols_list,' + str(root / 'exports.txt')])
            self.assertIn('metadata=identity', full)

    def test_replay_receipt_authenticates_two_raw_outputs_and_owned_compiler_commands(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            def write(path, data):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                return recipe.artifact(path)
            full = write(root / 'full-provider/libstd-hash.dylib', b'full')
            final = write(root / 'provider/libstd-hash.dylib', b'normalized')
            compiled = write(root / 'restricted-provider/libstd-hash.dylib', b'restricted')
            full_metadata = write(Path(full['path']).with_suffix('.rmeta'), b'exact metadata')
            restricted_metadata = write(Path(compiled['path']).with_suffix('.rmeta'), b'exact metadata')
            full_surface = self.provider()
            full_surface['install_id'] = full['path']
            consumers = self.consumers()
            for surface in consumers.values():
                surface['loads'] = [full['path']]
            closure = recipe.provider_export_closure(full_surface, consumers)
            restricted_surface = {**full_surface, 'install_id': compiled['path'],
                                  'exports': {s: full_surface['exports'][s] for s in closure['symbols']}}
            final_surface = {**restricted_surface, 'install_id': '@rpath/libstd-hash.dylib'}
            core = write(root.parent / 'libpython3.16.dylib', b'native Python')
            native_surface = {'install_id': '@rpath/libpython3.16.dylib', 'loads': [], 'exports': {'_PyList_New': 0}, 'imports': []}
            closure = recipe.provider_export_closure(full_surface, consumers, native_surface)
            export_file = write(root / 'provider-exports.txt', ''.join(s + '\n' for s in closure['symbols']).encode())
            original = ['rustc', '--crate-name', 'std', '--target', recipe.TARGET,
                        '--crate-type', 'rlib', '--out-dir', '/original', '-C', 'metadata=unchanged']
            full_argv = recipe.producer_arguments(original, Path(full['path']).parent)
            restricted_argv = recipe.restricted_producer_arguments(original, Path(compiled['path']).parent, Path(export_file['path']))
            policy = {'schema_version': 1, 'closure': closure, 'full_provider': full,
                      'full_metadata': full_metadata, 'restricted_metadata': restricted_metadata,
                      'exports_file': export_file, 'restricted_compiler_artifact': compiled,
                      'restricted_surface': restricted_surface, 'full_argv': full_argv,
                      'restricted_argv': restricted_argv, 'native_api': core}
            records = {name: {'compiler_artifact': write(root / ('lib' + name + '.dylib'), name.encode())}
                       for name in recipe.CONSUMERS}
            receipt = {'build': str(root.parent), 'export_policy': policy, 'provider': {**final, 'raw_artifact': {**compiled, 'path': final['path']}},
                       'runtime_pairs': {'std': [full['path'], full_metadata['path']]},
                       'consumers': records, 'units': [{'argv': original, 'query': False, 'exit_code': 0, 'reaped_exit': 0}],
                       'commands': [{'argv': argv, 'pid': 12345, 'pgid': 12345, 'exit_code': 0, 'reaped_exit': 0}
                                    for argv in (full_argv, restricted_argv)]}
            surfaces = {b'full': full_surface, b'restricted': restricted_surface, b'normalized': final_surface, b'native Python': native_surface,
                        **{name.encode(): surface for name, surface in consumers.items()}}
            with patch.object(recipe, 'macho_link_surface', side_effect=lambda data: surfaces[data]):
                recipe.verify_export_policy(receipt, root)
                receipt['commands'][1]['reaped_exit'] = 1
                with self.assertRaisesRegex(ValueError, 'compiler command'):
                    recipe.verify_export_policy(receipt, root)
                receipt['commands'][1]['reaped_exit'] = 0
                Path(compiled['path']).write_bytes(b'changed compiler output')
                with self.assertRaisesRegex(ValueError, 'artifact changed'):
                    recipe.verify_export_policy(receipt, root)

    def test_dynamic_python_lookup_requires_exact_bound_core_definition_not_name_prefix(self):
        consumers = self.consumers()
        consumers['_csv_rs']['imports'].append({'ordinal': -2, 'weak': False, 'symbol': '_PyList_New', 'addend': 0})
        core = {'install_id': '@rpath/libpython3.16.dylib', 'exports': {'_PyList_New': 0}}
        closure = recipe.provider_export_closure(self.provider(), consumers, core)
        self.assertNotIn('_PyList_New', closure['symbols'])
        for native in (None, {'exports': {}}, {'exports': {'_PyList_New': 4}}):
            with self.assertRaisesRegex(ValueError, 'native Python definition'):
                recipe.provider_export_closure(self.provider(), consumers, native)
        consumers['_csv_rs']['imports'][-1]['symbol'] = '__RNvneeded'
        with self.assertRaisesRegex(ValueError, 'native Python definition'):
            recipe.provider_export_closure(self.provider(), consumers, {'exports': {'__RNvneeded': 0}})

    def test_restricted_linker_replaces_one_generated_policy_without_appending_another(self):
        original = ['-dynamiclib', '-Wl,-exported_symbols_list', '-Wl,/owned/tmp/rustc123/list',
                    '-arch', 'arm64', '-o', '/owned/restricted-provider/libstd.dylib', '-Wl,-dead_strip']
        replaced, generated = recipe.replace_provider_export_argument(original, Path('/owned/provider-exports.txt'),
                                                                       Path('/owned/restricted-provider/libstd.dylib'))
        self.assertEqual(generated, Path('/owned/tmp/rustc123/list'))
        self.assertEqual(replaced, [original[0], original[1], '-Wl,/owned/provider-exports.txt', *original[3:]])
        self.assertEqual(original[2], '-Wl,/owned/tmp/rustc123/list')
        for invalid in (original + ['-Wl,-unexported_symbols_list,/other'],
                        original + original[1:3], original + ['@response'],
                        [*original[:2], '-Wl,/path,withcomma', *original[3:]],
                        [*original[:1], '-Wl,-exported_symbols_list,/combined', *original[3:]],
                        [*original[:1], '-Xlinker', '-exported_symbols_list', *original[3:]]):
            with self.assertRaises(ValueError):
                recipe.replace_provider_export_argument(invalid, Path('/owned/provider-exports.txt'),
                                                        Path('/owned/restricted-provider/libstd.dylib'))

    def test_restricted_system_import_subset_preserves_addends_and_original_identity(self):
        full = self.provider()
        closure = recipe.provider_export_closure(full, self.consumers())
        restricted = {**full, 'exports': {s: full['exports'][s] for s in closure['symbols']}, 'imports': []}
        recipe.verify_restricted_provider(full, restricted, closure, 'same', 'same')
        for change in ({'symbol': '_free'}, {'addend': 1}, {'weak': True}, {'ordinal': 0}):
            candidate = {**restricted, 'imports': [{**full['imports'][0], **change}]}
            with self.assertRaisesRegex(ValueError, 'import/dependency'):
                recipe.verify_restricted_provider(full, candidate, closure, 'same', 'same')
        with self.assertRaisesRegex(ValueError, 'import/dependency'):
            recipe.verify_restricted_provider(full, {**restricted, 'loads': ['/usr/lib/other.dylib']}, closure, 'same', 'same')

    def test_imported_tls_export_preserves_its_kind_through_replay_comparison(self):
        full = self.provider()
        full['exports']['__RNvneeded'] = 1
        closure = recipe.provider_export_closure(full, self.consumers())
        restricted = {**full, 'exports': {s: full['exports'][s] for s in closure['symbols']}}
        recipe.verify_restricted_provider(full, restricted, closure, 'same', 'same')
        restricted['exports']['__RNvneeded'] = 0
        with self.assertRaisesRegex(ValueError, 'export surface'):
            recipe.verify_restricted_provider(full, restricted, closure, 'same', 'same')

    def test_export_trie_flags_and_cycles_are_bounded(self):
        import _struct
        def image(trie):
            text = b'/owned/std.dylib\0'
            size = (24 + len(text) + 7) & ~7
            identity = _struct.pack('<6I', 13, size, 24, 0, 0, 0) + text + bytes(size - 24 - len(text))
            commands = identity + _struct.pack('<4I', 0x80000033, 16, 32 + size + 16, len(trie))
            return _struct.pack('<8I', 0xfeedfacf, 0x100000c, 0, 6, 2, len(commands), 0x80, 0) + commands + trie
        self.assertEqual(recipe.macho_link_surface(image(b'\0\1_x\0\6\2\4\0\0'))['exports'], {'_x': 4})
        self.assertEqual(recipe.macho_link_surface(image(b'\0\1_x\0\6\2\1\0\0'))['exports'], {'_x': 1})
        for trie in (b'\0\1_x\0\0', b'\0\1_x\0\6\2\10\0\0', b'\0\1_x\0\6\2\0',
                     *(b'\0\1_x\0\6\2' + bytes([flags]) + b'\0\0' for flags in (2, 5, 8, 16, 32))):
            with self.assertRaises(ValueError):
                recipe.macho_link_surface(image(trie))

    def test_macho_surface_rejects_truncated_unaligned_and_wrong_image_headers(self):
        import _struct
        def image(commands, count=1, kind=6):
            return _struct.pack('<8I', 0xfeedfacf, 0x100000c, 0, kind, count, len(commands), 0x80, 0) + commands
        for data in (b'', image(_struct.pack('<II', 2, 9) + b'x'),
                     image(_struct.pack('<II', 2, 24)), image(b'', 0, 8)):
            with self.assertRaises(ValueError):
                recipe.macho_link_surface(data)

    def test_classic_bindings_keep_provider_and_dynamic_python_ordinals_separate(self):
        import _struct
        def dylib(tag, name):
            text = name.encode() + b'\0'
            size = (24 + len(text) + 7) & ~7
            return _struct.pack('<6I', tag, size, 24, 0, 0, 0) + text + bytes(size - 24 - len(text))
        segment = _struct.pack('<II16s4Q4I', 0x19, 72, b'__DATA', 0x100000000, 4096, 0, 0, 3, 3, 0, 0)
        identity = dylib(13, '/owned/consumer.dylib')
        load = dylib(12, '/owned/full/libstd-hash.dylib')
        stream = b'\x11\x40__RNvneeded\0\x51\x70\0\x60\x7f\x90\x3e\x40_PyList_New\0\x60\0\x90\0'
        offset = 32 + len(segment + identity + load) + 48
        commands = segment + identity + load + _struct.pack('<12I', 0x80000022, 48, 0, 0, offset, len(stream), 0, 0, 0, 0, 0, 0)
        data = _struct.pack('<8I', 0xfeedfacf, 0x100000c, 0, 6, 4, len(commands), 0x80, 0) + commands + stream
        rows = recipe.macho_link_surface(data)['imports']
        self.assertEqual(rows, [{'ordinal': 1, 'weak': False, 'symbol': '__RNvneeded', 'addend': -1},
                                {'ordinal': -2, 'weak': False, 'symbol': '_PyList_New', 'addend': 0}])
        with self.assertRaises(ValueError):
            recipe.macho_link_surface(data[:-1])

    def chained_image(self, site_addend=0, table_addend=0, pointer_format=6, next_stride=0, import_index=0):
        import _struct
        def command(tag, name):
            text = name.encode() + b'\0'
            size = (24 + len(text) + 7) & ~7
            return _struct.pack('<6I', tag, size, 24, 0, 0, 0) + text + bytes(size - 24 - len(text))
        load = command(12, '/usr/lib/libSystem.B.dylib')
        identity = command(13, '/owned/libstd.dylib')
        site_offset = 32 + 72 + len(load) + len(identity) + 16
        starts = _struct.pack('<II', 1, 8) + _struct.pack('<IHHQIH', 24, 4096, pointer_format, 0, 0, 1) + _struct.pack('<H', site_offset)
        payload = (_struct.pack('<7I', 0, 28, 28 + len(starts), 36 + len(starts), 1, 2, 0)
                   + starts + _struct.pack('<Ii', 1 | (1 << 8), table_addend) + b'_malloc\0')
        offset = site_offset + 8
        segment = _struct.pack('<II16s4Q4I', 0x19, 72, b'__DATA', 0x100000000, 4096, 0, offset + len(payload), 3, 3, 0, 0)
        commands = segment + load + identity + _struct.pack('<4I', 0x80000034, 16, offset, len(payload))
        pointer = (1 << 63) | (next_stride << 51) | ((site_addend & 255) << 24) | import_index
        return (_struct.pack('<8I', 0xfeedfacf, 0x100000c, 0, 6, 4, len(commands), 0x80, 0)
                + commands + _struct.pack('<Q', pointer) + payload)

    def test_chained_pointer_site_addends_distinguish_identical_import_tables(self):
        zero = recipe.macho_link_surface(self.chained_image())['imports']
        positive = recipe.macho_link_surface(self.chained_image(site_addend=1))['imports']
        negative = recipe.macho_link_surface(self.chained_image(site_addend=1, table_addend=-5))['imports']
        self.assertEqual(zero[0]['addend'], 0)
        self.assertEqual(positive[0]['addend'], 1)
        self.assertEqual(negative[0]['addend'], -4)
        self.assertEqual(recipe.macho_link_surface(self.chained_image(site_addend=128))['imports'][0]['addend'], 128)
        self.assertEqual(recipe.macho_link_surface(self.chained_image(site_addend=255, table_addend=-5))['imports'][0]['addend'], 250)
        self.assertNotEqual(zero, positive)

    def test_chained_pointer_formats_and_site_bounds_fail_closed(self):
        for data in (self.chained_image(pointer_format=1), self.chained_image(import_index=1),
                     self.chained_image(next_stride=4095)):
            with self.assertRaises(ValueError):
                recipe.macho_link_surface(data)
        self.assertEqual(recipe.macho_link_surface(self.chained_image(pointer_format=2, site_addend=128))['imports'][0]['addend'], 128)

    def test_macho_surface_keeps_chained_import_ordinals_and_flags(self):
        data = self.chained_image()
        surface = recipe.macho_link_surface(data)
        self.assertEqual(surface['imports'], [{'ordinal': 1, 'weak': True, 'symbol': '_malloc', 'addend': 0}])
        self.assertEqual(surface['install_id'], '/owned/libstd.dylib')
        with self.assertRaises(ValueError):
            recipe.macho_link_surface(data[:-1])


if __name__ == '__main__':
    unittest.main()
