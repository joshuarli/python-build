"""Build only the macOS release CSV helper against one source-built abort std.

The ordinary workspace, helper bodies and Cargo lock are unchanged. Host build
scripts retain their installed host runtime. Target libraries instead receive
code and full metadata from a single freshly compiled standard-library graph.
"""
import os
import sys

if __name__ == '__main__':
    from csv_source_std_bootstrap import configure_bootstrap_path
    configure_bootstrap_path()

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tarfile
import tomllib

TARGET = 'aarch64-apple-darwin'
REVISION = '574ff7d98bd6d037e5236a8453029173b32631fd'
STD_LOCK_SHA256 = '75848db58a70444bfb62c649b103d19c5d92fede325eb0c8c0e5442848448669'
STD_ARCHIVE_SHA256 = 'dee5c574fab79b4b45aa24f7260613977d820e62013a7923647c066c10bdaec5'
RECIPE_ENVIRONMENT = ('SDKROOT', 'MACOSX_DEPLOYMENT_TARGET', 'CFLAGS', 'CPPFLAGS',
                      'LDFLAGS', 'ARCHFLAGS', 'PY_CC', 'PY_CPPFLAGS', 'PY_CFLAGS',
                      'PYTHON_BUILD_DIR', 'LLVM_TARGET', 'BINDGEN_EXTRA_CLANG_ARGS',
                      'LIBCLANG_PATH', 'RUST_SHARED_BUILD', 'BLDSHARED_EXE',
                      'BLDSHARED_ARGS', 'LIBPYTHON', 'DYLD_LIBRARY_PATH')


def recipe_environment(build, environment):
    from csv_source_std_bootstrap import build_library_path
    result = {k: environment.get(k) for k in RECIPE_ENVIRONMENT}
    result['DYLD_LIBRARY_PATH'] = build_library_path(build, environment)
    return result


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def artifact(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': digest(path), 'size': path.stat().st_size}


def jobserver_fds(flags):
    result = []
    for match in re.finditer(r'(?:^|\s)--jobserver-(?:fds|auth)=(\d+),(\d+)(?=\s|$)', flags):
        for raw in match.groups():
            fd = int(raw)
            if fd < 3:
                continue
            try:
                os.fstat(fd)
            except OSError:
                continue
            if fd not in result:
                result.append(fd)
    return tuple(result)


def is_query(args):
    return args in (['-vV'], ['--version']) or any(x == '--print' or x.startswith('--print=') for x in args)


def target_arguments(original, pairs, directories):
    args = list(original)
    if is_query(args) or '--target' not in args or args[args.index('--target') + 1] != TARGET:
        return args
    # An implicit no_std core from the installed sysroot cannot coexist with the
    # core carried by source std. Select all three identities explicitly.
    for name in ('std', 'core', 'alloc'):
        if any(x.split('=', 1)[0].split(':')[-1] == name for i, x in enumerate(args)
               if i and args[i - 1] == '--extern'):
            raise ValueError('unexpected existing runtime extern: ' + name)
    for name in ('std', 'core', 'alloc'):
        for path in pairs[name]:
            args.extend(['--extern', name + '=' + path])
    provider = str(Path(pairs['std'][0]).parent)
    for directory in dict.fromkeys([provider, *directories]):
        value = 'dependency=' + directory
        if not any(x == value for i, x in enumerate(args) if i and args[i - 1] == '-L'):
            args.extend(['-L', value])
    return args


def producer_arguments(original, output):
    args = []
    index = 0
    while index < len(original):
        value = original[index]
        if value == '--extern':
            name, raw = original[index + 1].split('=', 1)
            path = Path(raw)
            if path.suffix != '.rmeta' or not path.with_suffix('.rlib').is_file():
                raise ValueError('missing producer code/full metadata pair: ' + raw)
            # embed-metadata=no archives contain identity stubs, so both inputs
            # are necessary. Keep the private modifier exactly as Cargo emitted it.
            args.extend(['--extern', name + '=' + str(path.with_suffix('.rlib')), '--extern', original[index + 1]])
            index += 2
        elif value in ('--crate-type', '--out-dir'):
            args.extend([value, 'dylib' if value == '--crate-type' else str(output)])
            index += 2
        else:
            args.append(value)
            index += 1
    return args


def buildscript_environment(text):
    result = {}
    for line in text.splitlines():
        match = re.match(r'^cargo::?rustc-env=([^=]+)=(.*)$', line)
        if not match:
            continue
        name, value = match.groups()
        if name in result and result[name] != value:
            raise ValueError('conflicting buildscript environment: ' + name)
        result[name] = value
    return result


def select_std_unit(rows):
    candidates = [row for row in rows if '--crate-name' in row['argv']
                  and row['argv'][row['argv'].index('--crate-name') + 1] == 'std'
                  and '--target' in row['argv'] and not row['query']]
    if len(candidates) != 1 or candidates[0]['exit_code'] != 0 or candidates[0]['reaped_exit'] != 0:
        raise ValueError('expected one successful source std producer')
    return candidates[0]


def verify_files(files):
    for raw, expected in files.items():
        if digest(raw) != expected:
            raise ValueError('source std build input changed: ' + raw)


def native_prerequisite(modules, name):
    # The extension suffix follows a dot after the complete native module name;
    # a Rust helper with the same prefix is a different compiler input.
    candidates = list(modules.glob(name + '.*.so'))
    if len(candidates) != 1:
        raise ValueError('missing or ambiguous bootstrap native prerequisite: ' + name)
    return candidates[0]


def input_files(source, build, library, compiler):
    files = {}
    for directory in (source / 'Modules/_csv_rs', source / 'Modules/cpython-sys',
                      source / 'Modules/cpython-build-helper', source / 'Include', library):
        for path in sorted(directory.rglob('*')):
            if path.is_file():
                files[str(path.resolve())] = digest(path)
    for path in (source / 'Cargo.toml', source / 'Cargo.lock',
                 source / 'Python/stdlib_module_names.h', build / 'Makefile', build / 'pyconfig.h',
                 build / 'libpython3.16.dylib',
                 Path(compiler['rustc_path']), Path(compiler['cargo_path']), Path(__file__),
                 Path(__file__).with_name('csv_source_std_rustc.py'),
                 Path(__file__).with_name('csv_source_std_bootstrap.py'), Path(sys.executable)):
        files[str(path.resolve(strict=True))] = digest(path)
    for name in ('_posixsubprocess', 'math', 'select', '_struct', '_sha2', 'zlib', 'fcntl'):
        prerequisite = native_prerequisite(build / 'Modules', name)
        files[str(prerequisite.resolve(strict=True))] = digest(prerequisite)
    return files


def validate_vendor(library):
    lock = tomllib.loads((library / 'Cargo.lock').read_text())
    records, files = [], {}
    for package in lock['package']:
        if 'source' not in package:
            continue
        folder = library / 'vendor' / (package['name'] + '-' + package['version'])
        checksum = folder / '.cargo-checksum.json'
        checks = json.loads(checksum.read_text())
        if checks['package'] != package['checksum']:
            raise ValueError('stdlib vendor package checksum mismatch')
        for raw, expected in checks['files'].items():
            path = folder / raw
            if not path.resolve(strict=True).is_relative_to(folder.resolve()) or digest(path) != expected:
                raise ValueError('stdlib vendor file changed: ' + raw)
            files[str(path.resolve())] = expected
        files[str(checksum.resolve())] = digest(checksum)
        records.append({'name': package['name'], 'version': package['version'],
                        'source': package['source'], 'checksum': package['checksum']})
    return records, files


def runtime_artifacts(unit):
    args = unit['argv']
    name = args[args.index('--crate-name') + 1]
    extra = next(args[i + 1].split('=', 1)[1] for i, arg in enumerate(args[:-1])
                 if arg == '-C' and args[i + 1].startswith('extra-filename='))
    folder = Path(args[args.index('--out-dir') + 1])
    code = folder / ('lib' + name + extra + '.rlib')
    full = code.with_suffix('.rmeta')
    if not code.is_file() or not full.is_file():
        raise ValueError('missing exact runtime code/full metadata pair: ' + name)
    return code, full


def runtime_closure(std_unit, units):
    # Cargo also plans proc_macro and panic_unwind roots. Only the dependencies
    # reachable from this abort std producer belong to the transported runtime.
    candidates = [u for u in units if not u['query'] and '--target' in u['argv']
                  and '--crate-name' in u['argv'] and '--out-dir' in u['argv']]
    selected, pending = {}, [std_unit]
    while pending:
        unit = pending.pop()
        name = unit['argv'][unit['argv'].index('--crate-name') + 1]
        if name in selected:
            if selected[name] != unit:
                raise ValueError('ambiguous runtime compiler identity: ' + name)
            continue
        if unit['exit_code'] or unit['reaped_exit']:
            raise ValueError('failed runtime compiler unit')
        selected[name] = unit
        for i, arg in enumerate(unit['argv'][:-1]):
            if arg != '--extern':
                continue
            label, raw = unit['argv'][i + 1].split('=', 1)
            dependency = label.split(':')[-1]
            matches = [u for u in candidates
                       if u['argv'][u['argv'].index('--crate-name') + 1] == dependency
                       and Path(raw).parent == Path(u['argv'][u['argv'].index('--out-dir') + 1])]
            if len(matches) != 1:
                raise ValueError('runtime dependency lacks unique compiler receipt: ' + raw)
            pending.append(matches[0])
    if 'panic_unwind' in selected or 'proc_macro' in selected:
        raise ValueError('unexpected runtime root in abort std dependency closure')
    return list(selected.values())


def validate_csv_cache(source, cargo_home):
    packages = tomllib.loads((source / 'Cargo.lock').read_text())['package']
    selected = {}
    def visit(package):
        identity = (package['name'], package['version'])
        if identity in selected:
            return
        selected[identity] = package
        for raw in package.get('dependencies', []):
            fields = raw.split()
            matches = [p for p in packages if p['name'] == fields[0]
                       and (len(fields) < 2 or p['version'] == fields[1])]
            if len(matches) != 1:
                raise ValueError('ambiguous CSV lock dependency: ' + raw)
            visit(matches[0])
    visit(next(p for p in packages if p['name'] == '_csv_rs'))
    result, source_files = [], {}
    for package in selected.values():
        if 'source' not in package:
            continue
        matches = list((cargo_home / 'registry/cache').glob('*/' + package['name'] + '-' + package['version'] + '.crate'))
        if len(matches) != 1 or digest(matches[0]) != package['checksum']:
            raise ValueError('CSV registry archive missing or changed: ' + package['name'])
        archive = matches[0]
        result.append(artifact(archive))
        source_directory = cargo_home / 'registry/src' / archive.parent.name / (package['name'] + '-' + package['version'])
        # Cached extracted registry sources are independent files. Check them
        # against the checksum-verified archive before admitting compiler input.
        with tarfile.open(archive, 'r:gz') as stream:
            for member in stream.getmembers():
                parts = Path(member.name).parts
                if not parts or parts[0] != source_directory.name or '..' in parts:
                    raise ValueError('registry archive member outside package')
                if member.isdir():
                    continue
                if not member.isfile():
                    raise ValueError('registry archive member is not a regular file')
                path = source_directory.joinpath(*parts[1:])
                expected = hashlib.sha256(stream.extractfile(member).read()).hexdigest()
                if not path.is_file() or digest(path) != expected:
                    raise ValueError('cached CSV source differs from locked archive: ' + str(path))
                source_files[str(path.resolve())] = expected
    return result, source_files


def run(argv, cwd, environment, log, commands, timeout=180):
    log.parent.mkdir(parents=True, exist_ok=True)
    row = {'argv': list(map(str, argv)), 'cwd': str(cwd), 'environment': environment,
           'stdout': str(log.with_suffix('.stdout')), 'stderr': str(log.with_suffix('.stderr'))}
    with log.with_suffix('.stdout').open('w') as stdout, log.with_suffix('.stderr').open('w') as stderr:
        process = subprocess.Popen(row['argv'], cwd=cwd, env=environment, stdout=stdout, stderr=stderr,
                                   start_new_session=True, pass_fds=jobserver_fds(environment.get('CARGO_MAKEFLAGS', '')))
        row.update(pid=process.pid, pgid=os.getpgid(process.pid))
        try:
            row['exit_code'] = process.wait(timeout=timeout)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                row['killed'] = True
            row['reaped_exit'] = process.wait()
            commands.append(row)
    if row['exit_code'] != 0:
        raise RuntimeError('CSV source std command failed: ' + str(log))
    return log.with_suffix('.stdout').read_text()


def normalized_outputs(provider, csv, environment, commands, root):
    install_id = '@rpath/' + provider.name
    run(['/usr/bin/install_name_tool', '-id', install_id, provider], root, environment, root / 'logs/provider-id', commands)
    loads = run(['/usr/bin/otool', '-L', csv], root, environment, root / 'logs/csv-loads-before', commands)
    old = next((line.strip().split(' (')[0] for line in loads.splitlines()[1:]
                if provider.name in line), None)
    if old is None:
        raise ValueError('CSV does not link source std provider')
    if old != install_id:
        run(['/usr/bin/install_name_tool', '-change', old, install_id, csv], root, environment, root / 'logs/csv-provider-id', commands)
    rpath = '@loader_path/../../rust-cpython'
    run(['/usr/bin/install_name_tool', '-add_rpath', rpath, csv], root, environment, root / 'logs/csv-rpath', commands)
    for label, path in [('provider', provider), ('csv', csv)]:
        run(['/usr/bin/codesign', '--force', '--sign', '-', path], root, environment, root / ('logs/' + label + '-sign'), commands)
        run(['/usr/bin/codesign', '--verify', '--strict', path], root, environment, root / ('logs/' + label + '-verify'), commands)
    observed = {}
    for label, path in [('provider', provider), ('csv', csv)]:
        text = run(['/usr/bin/otool', '-L', path], root, environment, root / ('logs/' + label + '-loads-final'), commands)
        dependencies = [line.strip().split(' (')[0] for line in text.splitlines()[1:]]
        if label == 'provider':
            if not dependencies or dependencies.pop(0) != install_id:
                raise ValueError('provider install identity changed')
        elif dependencies.count(install_id) != 1:
            raise ValueError('CSV must reference exactly one source std provider')
        if any(not x.startswith(('/usr/lib/', '/System/Library/Frameworks/'))
               for x in dependencies if label != 'csv' or x != install_id):
            raise ValueError('unexpected non-system runtime dependency')
        commands_text = run(['/usr/bin/otool', '-l', path], root, environment, root / ('logs/' + label + '-commands-final'), commands)
        paths = re.findall(r'cmd LC_RPATH\s+cmdsize \d+\s+path (.*?) \(offset', commands_text)
        if paths != ([] if label == 'provider' else [rpath]):
            raise ValueError('unexpected runtime search path')
        observed[label] = dependencies
    return install_id, rpath, observed


def publish_build_mirror(provider, build):
    mirror_directory = build.parent / 'rust-cpython'
    if mirror_directory.exists() and mirror_directory.resolve() != mirror_directory:
        raise ValueError('build provider mirror has a symlink ancestor')
    owner = mirror_directory / '.csv-source-std-owner.json'
    expected = {'build': str(build.resolve())}
    if mirror_directory.exists():
        if not owner.is_file() or json.loads(owner.read_text()) != expected:
            raise ValueError('build provider mirror belongs to a different owner')
    else:
        mirror_directory.mkdir()
        owner.write_text(json.dumps(expected) + '\n')
    mirror = mirror_directory / provider.name
    if mirror.exists() and digest(mirror) != digest(provider):
        raise ValueError('build provider mirror collision')
    if not mirror.exists():
        shutil.copyfile(provider, mirror)
    return artifact(mirror)


def verify_build_receipt(source: Path, build: Path, target: str, source_metadata: dict) -> dict:
    source, build = source.resolve(), build.resolve()
    root = build / 'source-std338'
    receipt = json.loads((root / 'receipt.json').read_text())
    if receipt['schema_version'] != 1 or receipt['status'] != 'complete' or receipt['target'] != target:
        raise ValueError('incomplete CSV source std receipt')
    identity = receipt['source']
    if identity['path'] != str(source) or receipt['build'] != str(build):
        raise ValueError('CSV source/build owner mismatch')
    for key, field in [('sha256', 'std_archive_sha256'), ('compiler_revision', 'std_revision'),
                       ('library_cargo_lock_sha256', 'std_lock_sha256')]:
        if source_metadata[key] != identity[field]:
            raise ValueError('CSV std source identity mismatch: ' + key)
    if receipt['profile'] != 'release' or receipt['panic'] != 'abort' or receipt['allocator'] != 'System':
        raise ValueError('CSV source runtime policy changed')
    verify_files(identity['input_files'])
    verify_files(receipt['runtime_files'])
    for label in ('provider', 'csv'):
        record = receipt[label]
        path = Path(record['path'])
        if not path.resolve().is_relative_to(build) or artifact(path) != {k: record[k] for k in ('path', 'sha256', 'size')}:
            raise ValueError('CSV final artifact changed: ' + label)
    provider = Path(receipt['provider']['path'])
    if provider.parent != root / 'provider' or receipt['provider']['install_id'] != '@rpath/' + provider.name:
        raise ValueError('provider output placement or identity changed')
    if Path(receipt['csv']['path']) != build / 'target' / target / 'release/lib_csv_rs.dylib':
        raise ValueError('published CSV output placement changed')
    if receipt['csv']['rpath'] != '@loader_path/../../rust-cpython':
        raise ValueError('CSV runtime search path changed')
    mirror = Path(receipt['provider']['build_mirror_path'])
    if (mirror != build.parent / 'rust-cpython' / Path(receipt['provider']['path']).name
            or mirror.resolve(strict=True) != mirror
            or digest(mirror) != receipt['provider']['sha256']
            or receipt['provider']['build_mirror_sha256'] != receipt['provider']['sha256']):
        raise ValueError('build provider mirror changed')
    owner = mirror.parent / '.csv-source-std-owner.json'
    if json.loads(owner.read_text()) != {'build': str(build)}:
        raise ValueError('build provider mirror owner changed')
    for unit in receipt['units']:
        if unit['exit_code'] != 0 or unit['reaped_exit'] != 0:
            raise ValueError('failed compiler unit in completed receipt')
        verify_files(unit['source_files'])
    csv_unit = receipt['csv']['unit_receipt']
    if csv_unit not in receipt['units'] or csv_unit['query']:
        raise ValueError('CSV output lacks its successful compiler unit')
    for name, pair in receipt['runtime_pairs'].items():
        for raw in pair:
            if not any(x == name + '=' + raw for i, x in enumerate(csv_unit['argv'])
                       if i and csv_unit['argv'][i - 1] == '--extern'):
                raise ValueError('CSV compiler runtime pair missing: ' + name)
    if artifact(receipt['csv']['artifact_path'])['sha256'] != receipt['csv']['sha256']:
        raise ValueError('published CSV differs from final release artifact')
    for record in receipt['generated_bindings']:
        if artifact(record['path']) != record:
            raise ValueError('generated C API source changed')
    return receipt


class CompilerCleanupError(RuntimeError):
    def __init__(self, report):
        self.report = report
        super().__init__('compiler cleanup faults: ' + json.dumps(report['faults']))


def cleanup_compilers(root):
    # Wrapper children have independent process groups so a failed Cargo process
    # cannot leave native compiler descendants running after this recipe exits.
    report = {'groups': [], 'faults': []}
    for directory in ('std-units', 'csv-units'):
        for path in sorted((root / directory).glob('*.json')):
            try:
                row = json.loads(path.read_text())
                if not isinstance(row, dict):
                    raise ValueError('compiler receipt is not an object')
                if row.get('state') != 'running':
                    continue
                pgid = row['pgid']
                if type(pgid) is not int or pgid <= 1 or row.get('pid') != pgid:
                    raise ValueError('compiler group identity is invalid')
                try:
                    os.killpg(pgid, signal.SIGKILL)
                    result = 'kill_sent'
                except ProcessLookupError:
                    result = 'already_exited'
                report['groups'].append({'receipt': str(path), 'pgid': pgid, 'result': result})
            except (OSError, ValueError, KeyError, TypeError) as error:
                report['faults'].append({'receipt': str(path), 'error': repr(error)})
    if report['faults']:
        raise CompilerCleanupError(report)
    return report


def build_recipe(source, build, target, profile, jobs):
    if sys.platform != 'darwin' or target != TARGET or profile != 'release':
        raise ValueError('source std CSV recipe supports macOS arm64 release only')
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
    root = build / 'source-std338'
    if (root / 'receipt.json').is_file():
        receipt = verify_build_receipt(source, build, target, source_metadata)
        if receipt['recipe_environment'] != recipe_environment(build, os.environ):
            raise ValueError('completed CSV recipe compiler environment changed')
        return receipt
    if root.exists():
        raise ValueError('incomplete source std outputs exist; a clean build is required')
    root.mkdir()
    commands, units = [], []
    status = {'schema_version': 1, 'status': 'building', 'commands': commands}
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
        files[str(input_receipt)] = digest(input_receipt)
        std_registry, vendor_files = validate_vendor(library)
        files.update(vendor_files)
        registry, registry_sources = validate_csv_cache(source, Path(env['CARGO_HOME']))
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
        logger_source = Path(__file__).with_name('csv_source_std_rustc.py')
        logger.write_text('#!' + sys.executable + ' -E\n' + logger_source.read_text())
        logger.chmod(0o755)
        shutil.copyfile(Path(__file__), root / 'csv_source_std.py')
        bootstrap = Path(__file__).with_name('csv_source_std_bootstrap.py')
        shutil.copyfile(bootstrap, root / bootstrap.name)
        for copied in (logger, root / 'csv_source_std.py', root / bootstrap.name):
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
        provider_dir = root / 'provider'
        provider_dir.mkdir()
        replay = producer_arguments(original, provider_dir)
        run(replay, Path(std_unit['cwd']), source_env, root / 'logs/std-provider', commands)
        extra = next(original[i + 1].split('=', 1)[1] for i, x in enumerate(original[:-1])
                     if x == '-C' and original[i + 1].startswith('extra-filename='))
        provider = provider_dir / ('libstd' + extra + '.dylib')
        metadata = provider.with_suffix('.rmeta')
        pairs = {'std': [str(provider), str(metadata)]}
        directories = []
        runtime_files = {str(metadata): digest(metadata)}
        for unit in runtime_closure(std_unit, units):
            args = unit['argv']
            if unit['query'] or '--target' not in args or '--crate-name' not in args or '--out-dir' not in args:
                continue
            if unit['exit_code'] != 0 or unit['reaped_exit'] != 0:
                raise ValueError('failed source std dependency unit')
            code, full = runtime_artifacts(unit)
            directories.append(str(code.parent))
            runtime_files[str(code)] = digest(code)
            runtime_files[str(full)] = digest(full)
            name = args[args.index('--crate-name') + 1]
            if name in ('core', 'alloc'):
                if name in pairs:
                    raise ValueError('ambiguous source runtime pair')
                pairs[name] = [str(code), str(full)]
        if set(pairs) != {'std', 'core', 'alloc'}:
            raise ValueError('missing source runtime pair')
        config.update(target_directory=str(root / 'csv-target'), receipts=str(root / 'csv-units'),
                      runtime_pairs=pairs, runtime_directories=list(dict.fromkeys(directories)))
        config_path.write_text(json.dumps(config, indent=2) + '\n')
        csv_env = dict(env, CARGO_TARGET_DIR=config['target_directory'], CARGO_NET_OFFLINE='true',
                       RUSTC=str(logger), CSV_SOURCE_STD_RUSTC_CONFIG=str(config_path))
        csv_args = [cargo, 'build', '-vv', '--manifest-path', source / 'Cargo.toml', '--package', '_csv_rs',
                    '--target', target, '--release', '--locked', '--offline', '-j' + str(jobs),
                    '-Zhost-config', '-Ztarget-applies-to-host', '--config', 'target-applies-to-host=false',
                    '--config', 'host.linker=' + json.dumps(clang), '--config', 'target.' + target + '.linker=' + json.dumps(clang),
                    '--config', 'target.' + target + '.rustflags=' + json.dumps(flags)]
        run(csv_args, source, csv_env, root / 'logs/csv-build', commands, 900)
        # The normal build's member proof reads Cargo's real verbose transcript.
        # Reused outputs do not emit compiler evidence from a previous invocation.
        sys.stdout.write((root / 'logs/csv-build.stdout').read_text())
        sys.stderr.write((root / 'logs/csv-build.stderr').read_text())
        sys.stdout.flush()
        sys.stderr.flush()
        csv_units = [json.loads(p.read_text()) for p in (root / 'csv-units').glob('*.json')]
        if any(unit['exit_code'] != 0 or unit['reaped_exit'] != 0 for unit in csv_units):
            raise ValueError('failed CSV compiler unit')
        csv = root / 'csv-target' / target / 'release/lib_csv_rs.dylib'
        raw_provider, raw_csv = artifact(provider), artifact(csv)
        install_id, rpath, dependencies = normalized_outputs(provider, csv, env, commands, root)
        mirror = publish_build_mirror(provider, build)
        publish = build / 'target' / target / 'release/lib_csv_rs.dylib'
        publish.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(csv, publish)
        verify_files(files)
        verify_files(runtime_files)
        bindings = [unit['generated_c_api_before_compile'] for unit in csv_units if 'generated_c_api_before_compile' in unit]
        if len(bindings) != 1:
            raise ValueError('expected one fresh target C API generation')
        receipt = {'schema_version': 1, 'status': 'complete', 'build': str(build), 'target': target,
                   'recipe_environment': recipe_environment(build, inherited),
                   'profile': profile, 'panic': 'abort', 'allocator': 'System', 'compiler': compiler,
                   'source': {'path': str(source), 'workspace_lock_sha256': digest(source / 'Cargo.lock'),
                              'std_source_path': str(library), 'std_archive_sha256': STD_ARCHIVE_SHA256,
                              'std_revision': REVISION, 'std_lock_sha256': STD_LOCK_SHA256, 'input_files': files,
                              'input_receipt': artifact(input_receipt)},
                   'registry_archives': registry, 'std_registry_packages': std_registry, 'runtime_pairs': pairs, 'runtime_files': runtime_files,
                   'provider': {**artifact(provider), 'install_id': install_id, 'dependencies': dependencies['provider'],
                                'raw_artifact': raw_provider, 'build_mirror_path': mirror['path'],
                                'build_mirror_sha256': mirror['sha256']},
                   'csv': {**artifact(publish), 'artifact_path': str(csv), 'artifact_sha256': digest(csv),
                           'provider_install_id': install_id, 'rpath': rpath, 'raw_artifact': raw_csv,
                           'source': artifact(source / 'Modules/_csv_rs/src/lib.rs'),
                           'unit_receipt': next(unit for unit in csv_units if '--crate-name' in unit['argv']
                                                and unit['argv'][unit['argv'].index('--crate-name') + 1] == '_csv_rs')},
                   'generated_bindings': bindings, 'units': units + csv_units, 'commands': commands}
        (root / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        return verify_build_receipt(source, build, target, source_metadata)
    except BaseException as error:
        try:
            cleanup = cleanup_compilers(root)
        except CompilerCleanupError as cleanup_error:
            cleanup = cleanup_error.report
            error.add_note(str(cleanup_error))
            sys.stderr.write(str(cleanup_error) + '\n')
        status.update(status='failed', error=repr(error), commands=commands, units=units,
                      compiler_cleanup=cleanup)
        try:
            (root / 'failure.json').write_text(json.dumps(status, indent=2) + '\n')
        except OSError as receipt_error:
            error.add_note('failure receipt could not be written: ' + repr(receipt_error))
            sys.stderr.write('failure receipt could not be written: ' + repr(receipt_error) + '\n')
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['build'])
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--target', required=True)
    parser.add_argument('--profile', choices=['release'], required=True)
    parser.add_argument('--jobs', type=int, required=True)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('jobs must be positive')
    build_recipe(args.source, args.build, args.target, args.profile, args.jobs)


if __name__ == '__main__':
    main()
