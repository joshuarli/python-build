"""Build seven unchanged helpers and their source-built runtime into one image.

One original source std archive/full-metadata pair supplies every target crate.
Host build scripts and feature probes retain the installed runtime. A single
aggregate cdylib keeps seven separate initializers and module state contracts;
publication exposes one physical image through relative helper-name aliases.
"""
import os
import sys
from pathlib import Path
if __name__ == '__main__':
    from csv_source_std_bootstrap import configure_bootstrap_path
    configure_bootstrap_path()
sys.path.insert(0, str(Path(__file__).resolve().parent))
import json
import re
import shutil
import stat
import csv_source_std as std
from csv_source_aggregate_layout import verify_aggregate_layout, INIT_EXPORTS

if Path(std.__file__).resolve() != Path(__file__).resolve().with_name('csv_source_std.py'):
    raise ValueError('aggregate runtime helper has a different source owner')
TARGET = std.TARGET
CONSUMERS = std.CONSUMERS
PACKAGE = 'cpython-rust-source-aggregate356'
CRATE = 'cpython_rust_source_aggregate356'
BASENAME = 'lib' + CRATE + '.dylib'
INITS = INIT_EXPORTS
SCHEMA = 1
for _name in ('REVISION', 'STD_LOCK_SHA256', 'STD_ARCHIVE_SHA256', 'digest', 'artifact', 'run',
              'input_files', 'validate_vendor', 'validate_consumer_cache', 'recipe_environment',
              'buildscript_environment', 'select_std_unit', 'verify_files', 'cleanup_compilers', 'CompilerCleanupError'):
    globals()[_name] = getattr(std, _name)


def prepare_runtime(root, std_unit, std_units):
    if std.select_std_unit(std_units) != std_unit:
        raise ValueError('source runtime has a different original std compiler unit')
    types = [std_unit['argv'][i + 1] for i, arg in enumerate(std_unit['argv'][:-1]) if arg == '--crate-type']
    if types != ['rlib']:
        raise ValueError('aggregate requires original source std archive metadata')
    pairs, files, directories = {}, {}, []
    for unit in std.runtime_closure(std_unit, std_units):
        code, metadata = std.runtime_artifacts(unit)
        name = unit['argv'][unit['argv'].index('--crate-name') + 1]
        for path in (code, metadata):
            files[str(path)] = std.digest(path)
        directories.append(str(code.parent))
        if name in ('std', 'core', 'alloc'):
            if name in pairs:
                raise ValueError('ambiguous source runtime identity')
            pairs[name] = [str(code), str(metadata)]
    if set(pairs) != {'std', 'core', 'alloc'}:
        raise ValueError('incomplete static source runtime')
    view = std.create_target_sysroot(root, pairs, std_unit, std_units)
    return {'pairs': pairs, 'files': files, 'directories': list(dict.fromkeys(directories)), 'target_sysroot': view}


def consumer_arguments(cargo, source, jobs):
    return [cargo, 'build', '-vv', '--manifest-path', source / 'Cargo.toml', '--package', PACKAGE,
            '--target', TARGET, '--release', '--locked', '--offline', '-j' + str(jobs),
            '-Zhost-config', '-Ztarget-applies-to-host', '--config', 'target-applies-to-host=false']


def helper_dependencies(args):
    records = {}
    for name in CONSUMERS:
        values = [args[i + 1].split('=', 1)[1] for i, arg in enumerate(args[:-1])
                  if arg == '--extern' and args[i + 1].split('=', 1)[0] == name]
        metadata = [Path(value) for value in values if value.endswith('.rmeta')]
        if len(metadata) != 1:
            raise ValueError('aggregate helper lacks one full metadata argument: ' + name)
        code = metadata[0].with_suffix('.rlib')
        if any(value not in (str(code), str(metadata[0])) for value in values):
            raise ValueError('aggregate helper code/metadata identity changed: ' + name)
        pair = []
        for path in (code, metadata[0]):
            info = path.lstat()
            if path.resolve(strict=True) != path or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError('aggregate helper input is not canonical regular N1: ' + name)
            pair.append(artifact(path))
        records[name] = pair
    return records


def target_arguments(original, pairs, directories, target_sysroot):
    args = std.target_arguments(original, pairs, directories, target_sysroot)
    if '--crate-name' not in args or args[args.index('--crate-name') + 1] != CRATE:
        return args
    if any('prefer-dynamic' in arg for arg in args):
        raise ValueError('aggregate cannot prefer a dynamic runtime')
    dead_strip = [args[i + 1] for i, arg in enumerate(args[:-1])
                  if arg == '-C' and 'dead_strip_dylibs' in args[i + 1]]
    if dead_strip != ['link-arg=-Wl,-dead_strip_dylibs']:
        raise ValueError('aggregate root requires its exact dead-library policy')
    types = [args[i + 1] for i, arg in enumerate(args[:-1]) if arg == '--crate-type']
    if types != ['cdylib']:
        raise ValueError('aggregate root must emit one cdylib')
    dependencies = helper_dependencies(args)
    for name, (code, metadata) in dependencies.items():
        value = name + '=' + code['path']
        if value not in args:
            args.extend(['--extern', value])
    emit = [i for i, arg in enumerate(args) if arg.startswith('--emit=')]
    if len(emit) != 1 or args[emit[0]] not in ('--emit=dep-info,link', '--emit=dep-info,metadata,link'):
        raise ValueError('aggregate root emit policy changed')
    args[emit[0]] = '--emit=dep-info,metadata,link'
    return args


def logger_source():
    original = Path(std.__file__).with_name('csv_source_std_rustc.py').read_text()
    import_line = '    from csv_source_std import artifact, digest, host_capability_probe, is_query, jobserver_fds, target_arguments\n'
    before_receipt = "    receipts = Path(config['receipts'])\n"
    if original.count(import_line) != 1 or original.count(before_receipt) != 1:
        raise ValueError('frozen compiler logger source interface changed')
    original = original.replace(import_line, import_line + '    from csv_source_aggregate import target_arguments, helper_dependencies, CRATE\n')
    return original.replace(before_receipt,
        "    if not query and '--crate-name' in args and args[args.index('--crate-name') + 1] == CRATE:\n"
        "        row['aggregate_dependencies'] = helper_dependencies(args)\n" + before_receipt)


def verify_binding_surface(surface, native):
    if surface['loads'] != ['/usr/lib/libSystem.B.dylib']:
        raise ValueError('aggregate has a non-System runtime owner')
    for row in surface['imports']:
        if row['weak'] or row['ordinal'] not in (1, -2):
            raise ValueError('aggregate import has an unreviewed binding role')
        if row['ordinal'] == -2 and (not row['symbol'].startswith(('_Py', '__Py')) or native['exports'].get(row['symbol']) != 0):
            raise ValueError('aggregate Python lookup lacks its input-bound strong definition')
    extras = set(surface['exports']) - INITS
    for name in extras:
        allocator = any(re.fullmatch(r'__RNvCs[0-9A-Za-z]+_7___rustc' + str(len(root)) + '_' + re.escape(root), name)
                        for root in std.ALLOCATOR_EXPORT_ROOTS)
        metadata = re.fullmatch(r'_rust_metadata_(?:std|cpython_rust_source_aggregate356)_[0-9a-f]{16}', name)
        if not (allocator or metadata or name in (*std.EXPORT_SAFETY_ROOTS, *std.DARWIN_WEAK_EXPORTS)):
            raise ValueError('aggregate has an unproved compiler export: ' + name)
        expected = 4 if name in std.DARWIN_WEAK_EXPORTS else 0
        if surface['exports'][name] != expected:
            raise ValueError('aggregate compiler export role changed')
    return sorted(extras)


def select_graph(units, pairs, view, directories):
    selected = std.consumer_units(units, pairs, view)
    for name, unit in selected.items():
        types = [unit['argv'][i + 1] for i, arg in enumerate(unit['argv'][:-1]) if arg == '--crate-type']
        if types != ['rlib']:
            raise ValueError('aggregate helper emitted a separate image: ' + name)
        std.runtime_artifacts(unit)
    roots = [unit for unit in units if not unit['query'] and '--crate-name' in unit['argv']
             and unit['argv'][unit['argv'].index('--crate-name') + 1] == CRATE]
    if len(roots) != 1 or roots[0]['exit_code'] != 0 or roots[0]['reaped_exit'] != 0:
        raise ValueError('aggregate lacks one successful root compiler unit')
    root = roots[0]
    original = root['original_argv']
    expected = [original[0], *target_arguments(original[1:], pairs, directories, view)]
    if root['argv'] != expected:
        raise ValueError('aggregate root compiler arguments changed')
    dependencies = helper_dependencies(root['argv'])
    if root.get('aggregate_dependencies') != dependencies:
        raise ValueError('aggregate helper inputs changed since root compilation')
    for name, unit in selected.items():
        if dependencies[name] != [artifact(path) for path in std.runtime_artifacts(unit)]:
            raise ValueError('aggregate references a different helper compiler unit: ' + name)
    roots_in_argv = [root['argv'][i + 1] for i, arg in enumerate(root['argv'][:-1]) if arg == '--sysroot']
    if roots_in_argv != [str(view)] or any(arg.startswith('--sysroot=') for arg in root['argv']):
        raise ValueError('aggregate target sysroot changed')
    return selected, root


def publish_consumer(source, build, target, name, output, source_metadata, canonical=False):
    source, build, output = Path(source).resolve(), Path(build).resolve(), Path(output)
    expected = build / 'Modules' / BASENAME
    if target != TARGET or output.parent != build / 'Modules' or output.parent.resolve() != output.parent:
        raise ValueError('aggregate publication owner changed')
    if canonical:
        if name is not None or output != expected:
            raise ValueError('canonical aggregate publication path changed')
    elif name not in CONSUMERS or not output.name.startswith(name + '.') or not output.name.endswith('.so'):
        raise ValueError('aggregate alias is not a selected helper')
    receipt = verify_build_receipt(source, build, target, source_metadata)
    record = receipt['aggregate']
    if canonical:
        if output.is_symlink() or (output.exists() and (digest(output) != record['sha256'] or output.stat().st_size != record['size'])):
            raise ValueError('canonical aggregate publication changed')
        if not output.exists():
            with output.open('xb') as stream, Path(record['path']).open('rb') as original:
                shutil.copyfileobj(original, stream)
        if digest(output) != record['sha256']:
            raise ValueError('canonical aggregate copy changed')
    else:
        if expected.is_symlink() or not expected.is_file() or digest(expected) != record['sha256'] or expected.stat().st_size != record['size']:
            raise ValueError('canonical aggregate must publish before aliases')
        if output.is_symlink():
            if output.readlink() != Path(BASENAME):
                raise ValueError('aggregate alias target changed')
        elif output.exists():
            raise ValueError('aggregate alias cannot overwrite an existing module')
        else:
            output.symlink_to(BASENAME)
    return receipt

def build_recipe(source, build, target, profile, jobs):
    if sys.platform != 'darwin' or target != TARGET or profile != 'release':
        raise ValueError('source runtime aggregate supports macOS arm64 release only')
    source, build = source.resolve(strict=True), build.resolve(strict=True)
    library = Path(os.environ['PYTHON_BUILD_RUST_STD_SOURCE']).resolve(strict=True)
    if os.environ['PYTHON_BUILD_RUST_STD_REVISION'] != REVISION or os.environ['PYTHON_BUILD_RUST_STD_LOCK_SHA256'] != STD_LOCK_SHA256:
        raise ValueError('unexpected std source identity')
    if digest(library / 'Cargo.lock') != STD_LOCK_SHA256:
        raise ValueError('upstream std Cargo.lock changed')
    input_receipt = Path(os.environ['PYTHON_BUILD_RUST_STD_INPUT_RECEIPT']).resolve(strict=True)
    named_input = json.loads(input_receipt.read_text())
    if (named_input['schema'] != 1 or named_input['input']['sha256'] != STD_ARCHIVE_SHA256
            or named_input['compiler_revision'] != REVISION or named_input['library'] != str(library)
            or named_input['library_cargo_lock_sha256'] != STD_LOCK_SHA256):
        raise ValueError('named std source input receipt changed')
    source_metadata = {'sha256': STD_ARCHIVE_SHA256, 'compiler_revision': REVISION,
                       'library_cargo_lock_sha256': STD_LOCK_SHA256}
    root = build / 'source-aggregate356'
    if (root / 'receipt.json').is_file():
        receipt = verify_build_receipt(source, build, target, source_metadata)
        if receipt['recipe_environment'] != recipe_environment(build, os.environ):
            raise ValueError('completed aggregate compiler environment changed')
        return receipt
    if root.exists():
        raise ValueError('incomplete source std outputs exist; a clean build is required')
    std.check_fresh_consumer_outputs(build, target)
    root.mkdir()
    commands, units = [], []
    status = {'schema_version': SCHEMA, 'status': 'building', 'commands': commands}
    (root / 'logs').mkdir()
    (root / 'tmp').mkdir()
    inherited = dict(os.environ)
    env = {k: v for k, v in inherited.items() if k in {
        'PATH', 'HOME', 'LANG', 'LC_ALL', 'SDKROOT', 'MACOSX_DEPLOYMENT_TARGET', 'CFLAGS', 'CPPFLAGS',
        'LDFLAGS', 'ARCHFLAGS', 'PY_CC', 'PY_CPPFLAGS', 'PY_CFLAGS', 'PYTHON_BUILD_DIR', 'LLVM_TARGET',
        'BINDGEN_EXTRA_CLANG_ARGS', 'LIBCLANG_PATH', 'RUST_SHARED_BUILD', 'BLDSHARED_EXE', 'BLDSHARED_ARGS',
        'LIBPYTHON', 'CARGO_HOME', 'RUSTUP_HOME', 'RUSTUP_TOOLCHAIN'}}
    env['TMPDIR'] = str(root / 'tmp')
    from csv_source_std_bootstrap import build_library_path
    env['DYLD_LIBRARY_PATH'] = build_library_path(build, inherited)
    try:
        launcher = inherited.get('RUSTC') or shutil.which('rustc', path=env['PATH'])
        if not launcher:
            raise ValueError('normal rustc launcher missing')
        sysroot = Path(run([launcher, '--print', 'sysroot'], source, env, root / 'logs/sysroot', commands).strip())
        rustc, cargo = sysroot / 'bin/rustc', sysroot / 'bin/cargo'
        version = run([rustc, '-vV'], source, env, root / 'logs/rustc-version', commands)
        if 'commit-hash: ' + REVISION not in version or 'host: ' + TARGET not in version:
            raise ValueError('compiler does not match std source revision/host')
        compiler = {'rustc_path': str(rustc), 'rustc_sha256': digest(rustc), 'cargo_path': str(cargo),
                    'cargo_sha256': digest(cargo), 'commit_hash': REVISION, 'sysroot': str(sysroot)}
        files = input_files(source, build, library, compiler)
        for path in (Path(__file__), Path(__file__).with_name('csv_source_aggregate_layout.py'),
                     *(source / 'Modules' / PACKAGE / item for item in ('Cargo.toml', 'build.rs', 'src/lib.rs'))):
            files[str(path.resolve(strict=True))] = digest(path)
        files[str(input_receipt)] = digest(input_receipt)
        std_registry, vendor_files = validate_vendor(library)
        files.update(vendor_files)
        registry, registry_sources = validate_consumer_cache(source, Path(env['CARGO_HOME']))
        files.update(registry_sources)
        clang = env['PY_CC']
        if not Path(clang).is_file():
            raise ValueError('normal pinned PY_CC must name the compiler executable')
        for tool in (clang, '/usr/bin/otool', '/usr/bin/install_name_tool', '/usr/bin/codesign'):
            files[str(Path(tool).resolve(strict=True))] = digest(tool)
        env['PATH'] = str(rustc.parent) + ':' + str(Path(clang).parent) + ':/usr/bin:/bin:/usr/sbin:/sbin'
        if shutil.which('emcc', path=env['PATH']) is not None:
            raise ValueError('unexpected optional emcc provider')
        view = root / 'sysroot'
        (view / 'lib/rustlib/src/rust').mkdir(parents=True)
        (view / 'lib/rustlib/src/rust/library').symlink_to(library, target_is_directory=True)
        (view / 'lib/rustlib' / TARGET).symlink_to(sysroot / 'lib/rustlib' / TARGET, target_is_directory=True)
        probe = root / 'std-probe'
        probe.mkdir()
        (probe / 'Cargo.toml').write_text('[package]\nname="csv-source-std-probe"\nversion="0.0.0"\nedition="2024"\n[lib]\npath="lib.rs"\ncrate-type=["cdylib"]\n[profile.release]\npanic="abort"\n')
        (probe / 'lib.rs').write_text('#[unsafe(no_mangle)] pub extern "C" fn csv_source_std_probe() -> usize { std::thread::current().name().map_or(0, str::len) }\n')
        (probe / 'Cargo.lock').write_text('version = 4\n\n[[package]]\nname = "csv-source-std-probe"\nversion = "0.0.0"\n')
        for path in probe.iterdir():
            files[str(path)] = digest(path)
        config = {'rustc': str(rustc), 'rustc_sha256': digest(rustc), 'source_files': files,
                  'target_directory': str(root / 'std-target'), 'receipts': str(root / 'std-units'),
                  'runtime_pairs': None, 'runtime_directories': []}
        config_path = root / 'rustc-config.json'
        config_path.write_text(json.dumps(config, indent=2) + '\n')
        logger = root / 'rustc-logger.py'
        logger.write_text('#!' + sys.executable + ' -E\n' + logger_source())
        logger.chmod(0o755)
        shutil.copyfile(Path(std.__file__), root / 'csv_source_std.py')
        shutil.copyfile(Path(__file__), root / 'csv_source_aggregate.py')
        layout = Path(__file__).with_name('csv_source_aggregate_layout.py')
        shutil.copyfile(layout, root / layout.name)
        bootstrap = Path(__file__).with_name('csv_source_std_bootstrap.py')
        shutil.copyfile(bootstrap, root / bootstrap.name)
        for copied in (logger, root / 'csv_source_std.py', root / 'csv_source_aggregate.py', root / layout.name, root / bootstrap.name):
            files[str(copied)] = digest(copied)
        config_path.write_text(json.dumps(config, indent=2) + '\n')
        std_env = dict(env, CARGO_HOME=str(root / 'std-cargo-home'), CARGO_TARGET_DIR=config['target_directory'],
                       CARGO_NET_OFFLINE='true', RUSTC=str(logger), CSV_SOURCE_STD_RUSTC_CONFIG=str(config_path))
        flags = ['--sysroot', str(view), '-C', 'linker=' + clang]
        std_args = [cargo, 'build', '-vv', '--manifest-path', probe / 'Cargo.toml', '--release', '--locked', '--offline',
                    '--target', target, '-j' + str(jobs), '-Zbuild-std=std,panic_abort', '-Zbuild-std-features=backtrace',
                    '-Zhost-config', '-Ztarget-applies-to-host', '--config', 'target-applies-to-host=false',
                    '--config', 'host.linker=' + json.dumps(clang), '--config', 'target.' + target + '.linker=' + json.dumps(clang),
                    '--config', 'host.rustflags=' + json.dumps(flags), '--config', 'target.' + target + '.rustflags=' + json.dumps(flags),
                    '--config', 'source.crates-io.replace-with="csv-std-vendor"',
                    '--config', 'source.csv-std-vendor.directory=' + json.dumps(str(library / 'vendor'))]
        run(std_args, probe, std_env, root / 'logs/std-build', commands, 900)
        units = [json.loads(p.read_text()) for p in (root / 'std-units').glob('*.json')]
        std_unit = select_std_unit(units)
        original = std_unit['argv']
        source_env = dict(std_env, **std_unit['environment'])
        source_env.pop('CARGO_MAKEFLAGS', None)
        # This is Cargo's actual std buildscript output, not a guessed platform macro.
        script_outputs = list((root / 'std-target' / target / 'release/build/std').glob('*/run/stdout'))
        if len(script_outputs) != 1:
            raise ValueError('expected one std buildscript output')
        source_env.update(buildscript_environment(script_outputs[0].read_text()))
        runtime = prepare_runtime(root, std_unit, units)
        config.update(target_directory=str(root / 'consumer-target'), receipts=str(root / 'consumer-units'),
                      runtime_pairs=runtime['pairs'], runtime_directories=runtime['directories'],
                      target_sysroot=runtime['target_sysroot']['path'])
        config_path.write_text(json.dumps(config, indent=2) + '\n')
        consumer_env = dict(env, CARGO_TARGET_DIR=config['target_directory'], CARGO_NET_OFFLINE='true',
                            RUSTC=str(logger), CSV_SOURCE_STD_RUSTC_CONFIG=str(config_path))
        args = consumer_arguments(cargo, source, jobs) + [
            '--config', 'host.linker=' + json.dumps(clang),
            '--config', 'target.' + target + '.linker=' + json.dumps(clang),
            '--config', 'target.' + target + '.rustflags=' + json.dumps(flags)]
        run(args, source, consumer_env, root / 'logs/consumer-build', commands, 900)
        sys.stdout.write((root / 'logs/consumer-build.stdout').read_text())
        sys.stderr.write((root / 'logs/consumer-build.stderr').read_text())
        target_units = [json.loads(path.read_text()) for path in (root / 'consumer-units').glob('*.json')]
        std.verify_compiler_units(target_units, files, root / 'consumer-target')
        selected, aggregate_unit = select_graph(target_units, runtime['pairs'], runtime['target_sysroot']['path'], runtime['directories'])
        raw = std.runtime_output_paths(aggregate_unit)[0].with_suffix('.dylib')
        raw_metadata = raw.with_suffix('.rmeta')
        raw_record = artifact(raw)
        root_metadata = artifact(raw_metadata)
        native = artifact(build / 'libpython3.16.dylib')
        native_surface = std.macho_link_surface(Path(native['path']).read_bytes())
        raw_layout = verify_aggregate_layout(raw.read_bytes())
        extras = verify_binding_surface(raw_layout['link_surface'], native_surface)
        final = root / 'final' / BASENAME
        final.parent.mkdir()
        shutil.copyfile(raw, final)
        install_id = '@rpath/' + BASENAME
        run(['/usr/bin/install_name_tool', '-id', install_id, final], root, env, root / 'logs/aggregate-id', commands)
        run(['/usr/bin/codesign', '--force', '--sign', '-', final], root, env, root / 'logs/aggregate-sign', commands)
        run(['/usr/bin/codesign', '--verify', '--strict', final], root, env, root / 'logs/aggregate-sign-verify', commands)
        layout = verify_aggregate_layout(final.read_bytes())
        if (verify_binding_surface(layout['link_surface'], native_surface) != extras
                or layout['link_surface']['exports'] != raw_layout['link_surface']['exports']
                or layout['link_surface']['imports'] != raw_layout['link_surface']['imports']
                or layout['link_surface']['install_id'] != install_id):
            raise ValueError('normalized aggregate binding surface changed')
        release = build / 'target' / target / 'release' / BASENAME
        release.parent.mkdir(parents=True, exist_ok=True)
        if release.exists() or release.is_symlink():
            raise ValueError('aggregate release already exists')
        shutil.copyfile(final, release)
        aggregate = {**artifact(release), 'final_artifact': artifact(final), 'compiler_artifact': raw_record,
                     'metadata': root_metadata, 'unit_receipt': aggregate_unit, 'install_id': install_id,
                     'layout': layout, 'raw_layout': raw_layout, 'mandatory_exports': extras}
        consumers = {}
        for name, unit in selected.items():
            alias = release.parent / ('lib' + name + '.dylib')
            if alias.exists() or alias.is_symlink():
                raise ValueError('aggregate release alias already exists')
            alias.symlink_to(BASENAME)
            code, metadata = std.runtime_artifacts(unit)
            consumers[name] = {'path': str(alias), 'sha256': aggregate['sha256'], 'size': aggregate['size'],
                               'rlib': artifact(code), 'metadata': artifact(metadata), 'unit_receipt': unit}
        bindings = [unit['generated_c_api_before_compile'] for unit in target_units if 'generated_c_api_before_compile' in unit]
        if len(bindings) != 1:
            raise ValueError('aggregate requires one fresh typed C API generation')
        verify_files(files)
        verify_files(runtime['files'])
        if artifact(raw) != raw_record:
            raise ValueError('aggregate raw compiler artifact changed')
        std.verify_target_sysroot(root, runtime['target_sysroot'], runtime['pairs'], std_unit, units)
        receipt = {'schema_version': SCHEMA, 'status': 'complete', 'build': str(build), 'target': target,
                   'recipe_environment': recipe_environment(build, inherited), 'profile': profile,
                   'panic': 'abort', 'allocator': 'System', 'compiler': compiler,
                   'source': {'path': str(source), 'workspace_lock_sha256': digest(source / 'Cargo.lock'),
                              'std_source_path': str(library), 'std_archive_sha256': STD_ARCHIVE_SHA256,
                              'std_revision': REVISION, 'std_lock_sha256': STD_LOCK_SHA256, 'input_files': files,
                              'input_receipt': artifact(input_receipt)},
                   'registry_archives': registry, 'std_registry_packages': std_registry,
                   'runtime_pairs': runtime['pairs'], 'runtime_files': runtime['files'], 'runtime_directories': runtime['directories'],
                   'target_sysroot': runtime['target_sysroot'], 'aggregate': aggregate, 'native_api': native,
                   'consumers': consumers, 'generated_bindings': bindings, 'units': units + target_units, 'commands': commands}
        (root / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        return verify_build_receipt(source, build, target, source_metadata)
    except BaseException as error:
        try:
            cleanup = cleanup_compilers(root)
        except CompilerCleanupError as cleanup_error:
            cleanup = cleanup_error.report
            error.add_note(str(cleanup_error))
        status.update(status='failed', error=repr(error), commands=commands, units=units, compiler_cleanup=cleanup)
        try:
            (root / 'failure.json').write_text(json.dumps(status, indent=2) + '\n')
        except OSError as receipt_error:
            error.add_note('failure receipt could not be written: ' + repr(receipt_error))
        raise


def verify_build_receipt(source, build, target, source_metadata):
    source, build = Path(source).resolve(), Path(build).resolve()
    root = build / 'source-aggregate356'
    receipt = json.loads((root / 'receipt.json').read_text())
    if receipt['schema_version'] != SCHEMA or receipt['status'] != 'complete' or receipt['target'] != TARGET or target != TARGET:
        raise ValueError('incompatible aggregate receipt')
    identity = receipt['source']
    if identity['path'] != str(source) or receipt['build'] != str(build):
        raise ValueError('aggregate source/build owner changed')
    if receipt['profile'] != 'release' or receipt['panic'] != 'abort' or receipt['allocator'] != 'System':
        raise ValueError('aggregate runtime policy changed')
    for key, field in [('sha256', 'std_archive_sha256'), ('compiler_revision', 'std_revision'),
                       ('library_cargo_lock_sha256', 'std_lock_sha256')]:
        if source_metadata[key] != identity[field]:
            raise ValueError('aggregate source std identity changed')
    verify_files(identity['input_files'])
    verify_files(receipt['runtime_files'])
    std_unit = std.select_std_unit(receipt['units'])
    expected_pairs = {}
    expected_files = {}
    expected_directories = []
    for unit in std.runtime_closure(std_unit, receipt['units']):
        code, metadata = std.runtime_artifacts(unit)
        name = unit['argv'][unit['argv'].index('--crate-name') + 1]
        for path in (code, metadata):
            expected_files[str(path)] = digest(path)
        expected_directories.append(str(code.parent))
        if name in ('std', 'core', 'alloc'):
            if name in expected_pairs:
                raise ValueError('ambiguous aggregate source runtime')
            expected_pairs[name] = [str(code), str(metadata)]
    if (receipt['runtime_pairs'] != expected_pairs or receipt['runtime_files'] != expected_files
            or receipt['runtime_directories'] != list(dict.fromkeys(expected_directories))):
        raise ValueError('aggregate source runtime closure changed')
    std.verify_target_sysroot(root, receipt['target_sysroot'], expected_pairs, std_unit, receipt['units'])
    target_units = [unit for unit in receipt['units'] if any(Path(raw).is_relative_to(root / 'consumer-target')
                    for i, raw in enumerate(unit['argv']) if i and unit['argv'][i - 1] == '--out-dir')]
    std.verify_compiler_units(target_units, identity['input_files'], root / 'consumer-target')
    selected, aggregate_unit = select_graph(target_units, expected_pairs, receipt['target_sysroot']['path'], receipt['runtime_directories'])
    aggregate = receipt['aggregate']
    release = build / 'target' / target / 'release' / BASENAME
    raw = std.runtime_output_paths(aggregate_unit)[0].with_suffix('.dylib')
    if (aggregate['path'] != str(release) or release.is_symlink()
            or aggregate['final_artifact']['path'] != str(root / 'final' / BASENAME)
            or aggregate['compiler_artifact']['path'] != str(raw)
            or aggregate['metadata']['path'] != str(raw.with_suffix('.rmeta'))
            or aggregate['unit_receipt'] != aggregate_unit or aggregate['install_id'] != '@rpath/' + BASENAME):
        raise ValueError('aggregate image owner changed')
    for record in (aggregate['compiler_artifact'], aggregate['metadata'], aggregate['final_artifact'], receipt['native_api']):
        if artifact(record['path']) != record:
            raise ValueError('aggregate compiler/input artifact changed')
    if receipt['native_api']['path'] != str(build / 'libpython3.16.dylib'):
        raise ValueError('aggregate native Python owner changed')
    if artifact(release) != {key: aggregate[key] for key in ('path', 'sha256', 'size')}:
        raise ValueError('aggregate release artifact changed')
    if (aggregate['sha256'], aggregate['size']) != (aggregate['final_artifact']['sha256'], aggregate['final_artifact']['size']):
        raise ValueError('aggregate signed/release correspondence changed')
    native_surface = std.macho_link_surface(Path(receipt['native_api']['path']).read_bytes())
    layout = verify_aggregate_layout(release.read_bytes())
    raw_layout = verify_aggregate_layout(raw.read_bytes())
    if layout != aggregate['layout'] or raw_layout != aggregate['raw_layout']:
        raise ValueError('aggregate page/protection proof changed')
    if verify_binding_surface(layout['link_surface'], native_surface) != aggregate['mandatory_exports']:
        raise ValueError('aggregate binding proof changed')
    if (verify_binding_surface(raw_layout['link_surface'], native_surface) != aggregate['mandatory_exports']
            or layout['link_surface']['exports'] != raw_layout['link_surface']['exports']
            or layout['link_surface']['imports'] != raw_layout['link_surface']['imports']
            or layout['link_surface']['install_id'] != aggregate['install_id']):
        raise ValueError('aggregate compiler/final binding correspondence changed')
    if set(receipt['consumers']) != set(CONSUMERS):
        raise ValueError('aggregate helper roster changed')
    for name, record in receipt['consumers'].items():
        alias = release.parent / ('lib' + name + '.dylib')
        code, metadata = std.runtime_artifacts(selected[name])
        if (record['path'] != str(alias) or not alias.is_symlink() or alias.readlink() != Path(BASENAME)
                or alias.resolve(strict=True) != release or record['sha256'] != aggregate['sha256']
                or record['size'] != aggregate['size'] or record['rlib'] != artifact(code)
                or record['metadata'] != artifact(metadata) or record['unit_receipt'] != selected[name]):
            raise ValueError('aggregate helper compiler/alias owner changed: ' + name)
    if len(receipt['generated_bindings']) != 1:
        raise ValueError('aggregate typed C API generation changed')
    for record in receipt['generated_bindings']:
        if artifact(record['path']) != record:
            raise ValueError('aggregate typed C API bytes changed')
    return receipt


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('build', 'publish'))
    for option in ('source', 'build', 'target'):
        parser.add_argument('--' + option, required=True)
    parser.add_argument('--profile', default='release')
    parser.add_argument('--jobs', type=int, default=2)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--consumer', choices=CONSUMERS)
    group.add_argument('--canonical', action='store_true')
    parser.add_argument('--output')
    args = parser.parse_args()
    if args.command == 'build':
        build_recipe(Path(args.source), Path(args.build), args.target, args.profile, args.jobs)
    elif args.output and (args.canonical or args.consumer):
        metadata = {'sha256': STD_ARCHIVE_SHA256, 'compiler_revision': REVISION, 'library_cargo_lock_sha256': STD_LOCK_SHA256}
        publish_consumer(Path(args.source), Path(args.build), args.target, args.consumer, Path(args.output), metadata, args.canonical)
    else:
        parser.error('publish requires one exact canonical or selected helper output')


if __name__ == '__main__':
    main()
