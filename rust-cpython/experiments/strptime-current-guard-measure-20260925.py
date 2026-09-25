"""Bounded source-only measurement of the current numeric strptime guard."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import time

LANE = Path(__file__).resolve().parents[1]
BASE = Path('/Users/josh/d/python-build/rust-cpython/stage')
PINNED = Path('/Users/josh/d/python-build/rust-cpython/work/source-inspect/cpython-b812b4a7b9efaca46b98544a8633b7d7e454166b/Lib/_strptime.py')
PATCH = LANE / 'patches/0007-rust-strptime-numeric.patch'
MANIFEST = LANE / 'patches/manifest.json'
WORKLOAD = LANE / 'experiments/strptime_numeric_workload.py'
SCRATCH = LANE / 'work/strptime-current-guard-measure-20260925'
DATA = LANE / 'experiments/data/strptime-current-guard-measure-20260925.json'
EXPECTED = 'bb2b012282c2f8f0bad78f553fe946f3f093c96bfb8eca6a5077b5ee2e1a9473'
RUSTC = Path('/Users/josh/.rustup/toolchains/nightly-2026-09-15-aarch64-apple-darwin/bin/rustc')
CLANG = Path('/Users/josh/d/python-build/.cache/llvm/toolchains/23.1.2-d7c26fc6177e42842e2d1ffaad31aec057c56a924392b1a23d830abe2c5d53b1/bin/clang')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checkpoint(data):
    path = DATA.with_suffix('.json.tmp')
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
    path.replace(DATA)


def host():
    return {'load': subprocess.check_output(['uptime'], text=True).strip(),
            'swap': subprocess.check_output(['sysctl', 'vm.swapusage'], text=True).strip()}


def new_file(patch, name):
    section = patch.split(f'diff --git a/{name} b/{name}\n', 1)[1].split('diff --git ', 1)[0]
    return '\n'.join(line[1:] for line in section.splitlines()
                     if line.startswith('+') and not line.startswith('+++')) + '\n'


def attempt(command, env, name, kind, side=None):
    out = SCRATCH / f'{name}.stdout'
    err = SCRATCH / f'{name}.stderr'
    if out.exists() or err.exists():
        raise FileExistsError(name)
    start = time.perf_counter()
    with out.open('wb') as stdout, err.open('wb') as stderr:
        process = subprocess.Popen(command, env=env, stdout=stdout, stderr=stderr)
        _, status, usage = os.wait4(process.pid, 0)
    stdout = out.read_text(errors='replace')
    stderr = err.read_text(errors='replace')
    out.unlink()
    err.unlink()
    item = {'id': name, 'kind': kind, 'side': side, 'returncode': os.waitstatus_to_exitcode(status),
            'wall_seconds': time.perf_counter() - start, 'user_seconds': usage.ru_utime,
            'system_seconds': usage.ru_stime, 'peak_rss_bytes': usage.ru_maxrss,
            'swaps': usage.ru_nswap, 'process_count': 1}
    if item['returncode']:
        item['failure'] = {'stdout': stdout[-500:], 'stderr': stderr[-1000:]}
    elif kind in ('workload', 'memory'):
        try:
            item['output'] = json.loads(stdout)
            if item['output'] != {'count': 30000, 'rounds': 2, 'records': 60000,
                                  'buckets': 84, 'digest': EXPECTED}:
                item['failure'] = 'unexpected workload output'
        except json.JSONDecodeError:
            item['failure'] = 'invalid workload JSON: ' + stdout[-300:]
    elif kind == 'memory':
        pass
    else:
        item['output'] = stdout.strip()
    if kind == 'memory':
        for label, key, cast in (('user', 'timed_user_seconds', float), ('sys', 'timed_system_seconds', float),
                                  ('maximum resident set size', 'timed_peak_rss_bytes', int),
                                  ('peak memory footprint', 'peak_footprint_bytes', int), ('swaps', 'timed_swaps', int)):
            pattern = (rf'^{label} ([\d.]+)$' if label in ('user', 'sys')
                       else rf'^\s*(\d+)\s+{label}$')
            match = re.search(pattern, stderr, re.M)
            if match:
                item[key] = cast(match.group(1))
        if 'peak_footprint_bytes' not in item:
            item['failure'] = 'missing /usr/bin/time memory fields: ' + stderr[-1000:]
    return item


def main():
    if DATA.exists() or SCRATCH.exists():
        raise FileExistsError('run path already exists; preserve previous evidence')
    SCRATCH.mkdir(parents=True)
    data = {'recipe': {}, 'attempts': [], 'pairs': [], 'host_before': host()}
    checkpoint(data)
    try:
        source = BASE / 'lib/python3.16/_strptime.py'
        if sha(source) != sha(PINNED):
            raise ValueError('accepted parser does not match pinned source')
        patch = PATCH.read_text()
        selected = next(item for item in json.loads(MANIFEST.read_text())['patches'] if item['file'] == PATCH.name)
        if sha(PATCH) != selected['sha256']:
            raise ValueError('current patch does not match manifest')
        overlays = {side: SCRATCH / side for side in ('pure', 'guard')}
        for directory in overlays.values():
            directory.mkdir()
            shutil.copyfile(PINNED, directory / '_strptime.py')
        root = SCRATCH / 'patch-root'
        (root / 'Lib').mkdir(parents=True)
        shutil.copyfile(PINNED, root / 'Lib/_strptime.py')
        parser_patch = SCRATCH / 'parser.patch'
        parser_patch.write_text(patch.split('diff --git a/Makefile.pre.in', 1)[0])
        result = subprocess.run(['patch', '-p1', '--batch', '--forward', '-i', str(parser_patch)],
                                cwd=root, capture_output=True, text=True)
        data['attempts'].append({'id': 'parser-apply-01', 'kind': 'source', 'returncode': result.returncode,
                                 'output': (result.stdout + result.stderr)[-1000:]})
        checkpoint(data)
        if result.returncode:
            raise RuntimeError('parser hunk failed')
        shutil.copyfile(root / 'Lib/_strptime.py', overlays['guard'] / '_strptime.py')
        if sha(overlays['guard'] / '_strptime.py') == sha(PINNED):
            raise ValueError('parser hunk changed no bytes')
        native = SCRATCH / 'native'
        native.mkdir()
        sources = {}
        for name in ('module.c', 'scan.rs'):
            path = native / name
            path.write_text(new_file(patch, f'Modules/_rust_strptime_numeric/{name}'))
            sources[name] = sha(path)
        sdk = subprocess.check_output(['xcrun', '--sdk', 'macosx', '--show-sdk-path'], text=True).strip()
        archive = native / 'libstrptime_numeric.a'
        extension = overlays['guard'] / '_rust_strptime_numeric.cpython-316-darwin.so'
        commands = [
            [str(RUSTC), '--edition=2024', '--crate-type=staticlib', '-C', 'opt-level=3', '-C', 'panic=abort', str(native / 'scan.rs'), '-o', str(archive)],
            [str(CLANG), '-O3', '-mcpu=apple-m1', '-fPIC', '-mmacosx-version-min=26.0', '-isysroot', sdk,
             '-bundle', '-undefined', 'dynamic_lookup', '-I', str(BASE / 'include/python3.16'),
             str(native / 'module.c'), str(archive), '-o', str(extension)],
        ]
        data['recipe'] = {'pinned_commit': 'b812b4a7b9efaca46b98544a8633b7d7e454166b',
                          'interpreter_sha256': sha(BASE / 'bin/python3.16'),
                          'pinned_source_sha256': sha(PINNED), 'pure_source_sha256': sha(overlays['pure'] / '_strptime.py'),
                          'guard_source_sha256': sha(overlays['guard'] / '_strptime.py'),
                          'patch_sha256': sha(PATCH), 'manifest_sha256': sha(MANIFEST),
                          'native_source_sha256': sources, 'workload_sha256': sha(WORKLOAD),
                          'compiler_commands': commands, 'sdk': sdk,
                          'workload_command': 'same accepted python3.16 -S -B strptime_numeric_workload.py --count 30000 --rounds 2',
                          'environment': {'PYTHONHASHSEED': '1', 'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1'},
                          'cache_policy': 'fresh empty PYTHONPYCACHEPREFIX, -B; both overlays compile source; no pyc files',
                          'timing_method': 'perf_counter wall and os.wait4 direct child CPU/RSS/swap; Python workload has no children',
                          'memory_method': '/usr/bin/time -l -p separately for physical footprint and direct child peak RSS',
                          'order': '2 pure/pure self pairs; 5 counterbalanced pure/guard pairs; 3 separate memory pairs'}
        checkpoint(data)
        for index, command in enumerate(commands, 1):
            item = attempt(command, os.environ.copy(), f'compiler-{index:02d}', 'compiler')
            data['attempts'].append(item)
            checkpoint(data)
            if item.get('failure'):
                raise RuntimeError(item['id'])
        data['recipe']['archive_sha256'] = sha(archive)
        data['recipe']['extension_sha256'] = sha(extension)
        checkpoint(data)
        cache = SCRATCH / 'empty-pycache'
        cache.mkdir()
        env = os.environ.copy()
        for key in tuple(env):
            if key in ('PYTHONPATH', 'PYTHONPYCACHEPREFIX') or key.startswith('DYLD_'):
                env.pop(key)
        env.update(PYTHONHASHSEED='1', PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1',
                   PYTHONPYCACHEPREFIX=str(cache))
        for side in ('pure', 'guard'):
            command = [str(BASE / 'bin/python3.16'), '-S', '-B', '-c',
                       'import datetime,_strptime,sys,pathlib; datetime.datetime.strptime("2024/03/17 11:22:33","%Y/%m/%d %H:%M:%S"); datetime.datetime.strptime("2024/03/17 11:22:33","%Y/%m/%d %H:%M:%S"); print(_strptime.__file__); print(getattr(sys.modules.get("_rust_strptime_numeric"),"__file__","absent")); print(pathlib.Path(getattr(_strptime,"__cached__","")).exists() if getattr(_strptime,"__cached__",None) else False)']
            item = attempt(command, env | {'PYTHONPATH': str(overlays[side])}, f'import-{side}', 'probe', side)
            data['attempts'].append(item)
            checkpoint(data)
            expected = f'{overlays[side] / "_strptime.py"}\n{extension if side == "guard" else "absent"}\nFalse'
            if item.get('failure') or item['output'] != expected:
                raise RuntimeError(f'import identity failed: {side}: {item.get("output")}')
        if any(cache.rglob('*.pyc')):
            raise ValueError('unexpected pyc after probe')
        reference = None
        for family, count in (('self', 2), ('comparison', 5), ('memory', 3)):
            for number in range(1, count + 1):
                sides = ('pure', 'pure') if family == 'self' else (('pure', 'guard') if number % 2 else ('guard', 'pure'))
                group = {'family': family, 'number': number, 'order': sides, 'host_before': host(), 'attempts': []}
                data['pairs'].append(group)
                checkpoint(data)
                for position, side in enumerate(sides, 1):
                    command = [str(BASE / 'bin/python3.16'), '-S', '-B', str(WORKLOAD), '--count', '30000', '--rounds', '2']
                    if family == 'memory':
                        command = ['/usr/bin/time', '-l', '-p', *command]
                    item = attempt(command, env | {'PYTHONPATH': str(overlays[side])},
                                   f'{family}-{number:02d}-{position:02d}-{side}', family if family == 'memory' else 'workload', side)
                    data['attempts'].append(item)
                    group['attempts'].append(item['id'])
                    checkpoint(data)
                    if item.get('failure'):
                        raise RuntimeError(item['id'])
                    if reference is None:
                        reference = item['output']
                    elif item['output'] != reference:
                        item['failure'] = 'output differs from first pure run'
                        checkpoint(data)
                        raise RuntimeError(item['id'])
                group['host_after'] = host()
                checkpoint(data)
        if any(cache.rglob('*.pyc')):
            raise ValueError('unexpected pyc after benchmark')
        by_id = {item['id']: item for item in data['attempts']}
        summary = {}
        for family in ('self', 'comparison'):
            ratios = {'wall': [], 'cpu': []}
            for group in (group for group in data['pairs'] if group['family'] == family):
                first, second = (by_id[name] for name in group['attempts'])
                guard, pure = ((second, first) if family == 'self' else
                               (next(item for item in (first, second) if item['side'] == 'guard'),
                                next(item for item in (first, second) if item['side'] == 'pure')))
                ratios['wall'].append(guard['wall_seconds'] / pure['wall_seconds'])
                ratios['cpu'].append((guard['user_seconds'] + guard['system_seconds']) /
                                     (pure['user_seconds'] + pure['system_seconds']))
            summary[family] = {key: {'ratios': values, 'median': statistics.median(values),
                                      'range': [min(values), max(values)]} for key, values in ratios.items()}
        deltas = []
        for group in (group for group in data['pairs'] if group['family'] == 'memory'):
            sides = {by_id[name]['side']: by_id[name] for name in group['attempts']}
            deltas.append({'rss_bytes': sides['guard']['timed_peak_rss_bytes'] - sides['pure']['timed_peak_rss_bytes'],
                           'footprint_bytes': sides['guard']['peak_footprint_bytes'] - sides['pure']['peak_footprint_bytes']})
        summary['memory_deltas'] = deltas
        data['summary'] = summary
        checkpoint(data)
    except Exception as error:
        data['failure'] = repr(error)
        checkpoint(data)
        raise
    finally:
        data['host_after'] = host()
        checkpoint(data)


def resume():
    if not DATA.exists():
        raise FileNotFoundError(DATA)
    data = json.loads(DATA.read_text())
    if data.get('pairs'):
        raise ValueError('measurement pairs already started')
    data['recovered_failure'] = data.pop('failure', None)
    data['resume_host_before'] = host()
    checkpoint(data)
    overlays = {side: SCRATCH / side for side in ('pure', 'guard')}
    extension = overlays['guard'] / '_rust_strptime_numeric.cpython-316-darwin.so'
    cache = SCRATCH / 'empty-pycache'
    if any(cache.rglob('*.pyc')):
        raise ValueError('unexpected existing pyc')
    env = os.environ.copy()
    for key in tuple(env):
        if key in ('PYTHONPATH', 'PYTHONPYCACHEPREFIX') or key.startswith('DYLD_'):
            env.pop(key)
    env.update(PYTHONHASHSEED='1', PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1',
               PYTHONPYCACHEPREFIX=str(cache))
    try:
        for side in ('pure', 'guard'):
            command = [str(BASE / 'bin/python3.16'), '-S', '-B', '-c',
                       'import datetime,_strptime,sys,pathlib; datetime.datetime.strptime("2024/03/17 11:22:33","%Y/%m/%d %H:%M:%S"); datetime.datetime.strptime("2024/03/17 11:22:33","%Y/%m/%d %H:%M:%S"); print(_strptime.__file__); print(getattr(sys.modules.get("_rust_strptime_numeric"),"__file__","absent")); print(pathlib.Path(getattr(_strptime,"__cached__","")).exists() if getattr(_strptime,"__cached__",None) else False)']
            item = attempt(command, env | {'PYTHONPATH': str(overlays[side])}, f'import-02-{side}', 'probe', side)
            data['attempts'].append(item)
            checkpoint(data)
            expected = f'{overlays[side] / "_strptime.py"}\n{extension if side == "guard" else "absent"}\nFalse'
            if item.get('failure') or item['output'] != expected:
                raise RuntimeError(f'import identity failed: {side}: {item.get("output")}')
        reference = None
        for family, count in (('self', 2), ('comparison', 5), ('memory', 3)):
            for number in range(1, count + 1):
                sides = ('pure', 'pure') if family == 'self' else (('pure', 'guard') if number % 2 else ('guard', 'pure'))
                group = {'family': family, 'number': number, 'order': sides, 'host_before': host(), 'attempts': []}
                data['pairs'].append(group)
                checkpoint(data)
                for position, side in enumerate(sides, 1):
                    command = [str(BASE / 'bin/python3.16'), '-S', '-B', str(WORKLOAD), '--count', '30000', '--rounds', '2']
                    if family == 'memory':
                        command = ['/usr/bin/time', '-l', '-p', *command]
                    item = attempt(command, env | {'PYTHONPATH': str(overlays[side])},
                                   f'{family}-{number:02d}-{position:02d}-{side}', family if family == 'memory' else 'workload', side)
                    data['attempts'].append(item)
                    group['attempts'].append(item['id'])
                    checkpoint(data)
                    if item.get('failure'):
                        raise RuntimeError(item['id'])
                    if reference is None:
                        reference = item['output']
                    elif item['output'] != reference:
                        item['failure'] = 'output differs from first pure run'
                        checkpoint(data)
                        raise RuntimeError(item['id'])
                group['host_after'] = host()
                checkpoint(data)
        if any(cache.rglob('*.pyc')):
            raise ValueError('unexpected pyc after benchmark')
        by_id = {item['id']: item for item in data['attempts']}
        summary = {}
        for family in ('self', 'comparison'):
            ratios = {'wall': [], 'cpu': []}
            for group in (group for group in data['pairs'] if group['family'] == family):
                first, second = (by_id[name] for name in group['attempts'])
                guard, pure = ((second, first) if family == 'self' else
                               (next(item for item in (first, second) if item['side'] == 'guard'),
                                next(item for item in (first, second) if item['side'] == 'pure')))
                ratios['wall'].append(guard['wall_seconds'] / pure['wall_seconds'])
                ratios['cpu'].append((guard['user_seconds'] + guard['system_seconds']) /
                                     (pure['user_seconds'] + pure['system_seconds']))
            summary[family] = {key: {'ratios': values, 'median': statistics.median(values),
                                      'range': [min(values), max(values)]} for key, values in ratios.items()}
        deltas = []
        for group in (group for group in data['pairs'] if group['family'] == 'memory'):
            sides = {by_id[name]['side']: by_id[name] for name in group['attempts']}
            deltas.append({'rss_bytes': sides['guard']['timed_peak_rss_bytes'] - sides['pure']['timed_peak_rss_bytes'],
                           'footprint_bytes': sides['guard']['peak_footprint_bytes'] - sides['pure']['peak_footprint_bytes']})
        summary['memory_deltas'] = deltas
        data['summary'] = summary
        checkpoint(data)
    except Exception as error:
        data['failure'] = repr(error)
        checkpoint(data)
        raise
    finally:
        data['host_after'] = host()
        checkpoint(data)


if __name__ == '__main__':
    import sys
    if sys.argv[1:] == ['--resume']:
        resume()
    else:
        main()
