"""Measure the current optional IPv4 guard on one accepted CPython executable."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import time

from evidence_checkpoint import checkpoint_evidence, reserve_evidence


LANE = Path(__file__).resolve().parents[1]
BASE = Path('/Users/josh/d/python-build/rust-cpython/stage')
PATCH = LANE / 'patches/0006-rust-ipv4-scan.patch'
WORKLOAD = LANE / 'experiments/ipaddress_v4_workload.py'
SCRATCH = LANE / 'work/ipv4-current-guard-measure-20260925'
DATA = LANE / 'experiments/data/ipv4-current-guard-measure-20260925.json'
EVIDENCE = DATA
EXPECTED_DIGEST = '71b21698342ecd72171e968712cf7218d0272ea3cbc856e94797a428a0218180'
PURE_SHA = '6e800cb5727ac9ea045d406873a7dfb37f1be01ef5a8a1df52d6399635995a79'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checkpoint(data):
    checkpoint_evidence(EVIDENCE, data, sort_keys=True)


def host():
    return {'uptime': subprocess.check_output(['uptime'], text=True).strip(),
            'swap': subprocess.check_output(['sysctl', 'vm.swapusage'], text=True).strip()}


def extract_new_file(patch, name):
    section = patch.split(f'diff --git a/{name} b/{name}\n', 1)[1].split('diff --git ', 1)[0]
    return '\n'.join(line[1:] for line in section.splitlines()
                     if line.startswith('+') and not line.startswith('+++')) + '\n'


def measure(command, env, attempt_id, kind):
    out = SCRATCH / f'{attempt_id}.stdout'
    err = SCRATCH / f'{attempt_id}.stderr'
    started = time.perf_counter()
    with out.open('wb') as stdout, err.open('wb') as stderr:
        child = subprocess.Popen(command, env=env, stdout=stdout, stderr=stderr)
        _, status, usage = os.wait4(child.pid, 0)
    record = {'id': attempt_id, 'kind': kind, 'returncode': os.waitstatus_to_exitcode(status),
              'wall_seconds': time.perf_counter() - started, 'user_seconds': usage.ru_utime,
              'system_seconds': usage.ru_stime, 'peak_rss_bytes': usage.ru_maxrss,
              'swaps': usage.ru_nswap, 'process_count': 1}
    stdout_text = out.read_text(errors='replace')
    stderr_text = err.read_text(errors='replace')
    out.unlink()
    err.unlink()
    if kind == 'workload' and record['returncode'] == 0:
        try:
            output = json.loads(stdout_text)
            record['output'] = output
            if output.get('digest') != EXPECTED_DIGEST or output.get('count') != 30000 or output.get('rounds') != 2:
                record['failure'] = 'workload output identity differs'
        except json.JSONDecodeError:
            record['failure'] = 'invalid workload JSON: ' + stdout_text[-300:]
    elif record['returncode'] or kind == 'probe' and not stdout_text.strip():
        record['failure'] = {'stdout_tail': stdout_text[-500:], 'stderr_tail': stderr_text[-1000:]}
    elif kind == 'probe':
        record['output'] = stdout_text.strip()
    return record


def main(evidence_path, scratch_path):
    global EVIDENCE, SCRATCH
    EVIDENCE = evidence_path
    SCRATCH = scratch_path
    if SCRATCH.exists():
        raise FileExistsError(f'scratch already exists: {SCRATCH}; choose a new --scratch path')
    reserve_evidence(EVIDENCE)
    SCRATCH.mkdir(parents=True)
    data = {'recipe': {}, 'build': {}, 'attempts': [], 'pairs': [], 'host_before': host()}
    checkpoint(data)
    try:
        pure = BASE / 'lib/python3.16/ipaddress.py'
        pinned = SCRATCH / 'pinned-ipaddress.py'
        if not pinned.exists():
            shutil.copyfile(pure, pinned)
        if sha(pure) != PURE_SHA or sha(pinned) != PURE_SHA:
            raise ValueError('accepted and pinned parsers differ from the locked source')
        overlays = {side: SCRATCH / side for side in ('pure', 'guard')}
        for side, directory in overlays.items():
            directory.mkdir(exist_ok=True)
            shutil.copyfile(pinned, directory / 'ipaddress.py')
        patch_text = PATCH.read_text()
        parser_patch = patch_text.split('diff --git a/Makefile.pre.in', 1)[0]
        parser_patch_path = SCRATCH / 'parser.patch'
        parser_patch_path.write_text(parser_patch)
        guard = overlays['guard'] / 'ipaddress.py'
        # The patch addresses Lib/ipaddress.py, so apply it in an isolated Lib overlay.
        guard_lib = SCRATCH / 'patch-root/Lib'
        guard_lib.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pinned, guard_lib / 'ipaddress.py')
        applied = subprocess.run(['patch', '-p1', '--batch', '-i', str(parser_patch_path)],
                                 cwd=guard_lib.parent, capture_output=True, text=True)
        if applied.returncode:
            raise ValueError('current parser hunk failed: ' + applied.stdout + applied.stderr)
        shutil.copyfile(guard_lib / 'ipaddress.py', guard)
        native = SCRATCH / 'native'
        native.mkdir(exist_ok=True)
        sources = {}
        for name in ('module.c', 'scan.rs'):
            path = native / name
            path.write_text(extract_new_file(patch_text, f'Modules/_rust_ipv4_scan/{name}'))
            sources[name] = sha(path)
        archive = native / 'libipv4_scan.a'
        extension = overlays['guard'] / '_rust_ipv4_scan.cpython-316-darwin.so'
        clang = Path('/Users/josh/d/python-build/.cache/llvm/toolchains/23.1.2-d7c26fc6177e42842e2d1ffaad31aec057c56a924392b1a23d830abe2c5d53b1/bin/clang')
        sdk = subprocess.check_output(['xcrun', '--sdk', 'macosx', '--show-sdk-path'], text=True).strip()
        commands = [
            ['rustup', 'run', 'nightly-2026-09-15', 'rustc', '--edition=2024', '--crate-type=staticlib', '-C', 'opt-level=3', '-C', 'panic=abort', str(native / 'scan.rs'), '-o', str(archive)],
            [str(clang), '-O3', '-mcpu=apple-m1', '-fPIC', '-mmacosx-version-min=26.0', '-isysroot', sdk, '-bundle', '-undefined', 'dynamic_lookup', '-I', str(BASE / 'include/python3.16'), str(native / 'module.c'), str(archive), '-o', str(extension)],
        ]
        data['recipe'] = {'pinned_cpython_commit': 'b812b4a7b9efaca46b98544a8633b7d7e454166b',
                          'interpreter_sha256': sha(BASE / 'bin/python3.16'),
                          'pure_parser_sha256': sha(overlays['pure'] / 'ipaddress.py'),
                          'guard_parser_sha256': sha(guard), 'patch_sha256': sha(PATCH),
                          'workload_sha256': sha(WORKLOAD), 'native_source_sha256': sources,
                          'compiler_commands': commands, 'sdk': sdk,
                          'timing_command': 'same accepted python3.16 -S -B ipaddress_v4_workload.py --count 30000 --rounds 2; PYTHONPATH selects overlay',
                          'cache_policy': 'empty PYTHONPYCACHEPREFIX; -B and PYTHONDONTWRITEBYTECODE=1; both compile source',
                          'measurement': 'direct os.wait4 per single process, perf_counter for wall; wait4 maximum RSS and swaps',
                          'order': '2 pure/pure, 2 guard/guard, 5 counterbalanced pure/guard pairs'}
        checkpoint(data)
        for index, command in enumerate(commands, 1):
            record = measure(command, os.environ.copy(), f'build-{index:02d}', 'build')
            data['build'][f'step_{index}'] = record
            checkpoint(data)
            if record.get('failure'):
                raise RuntimeError(f'build step {index} failed')
        data['recipe']['archive_sha256'] = sha(archive)
        data['recipe']['extension_sha256'] = sha(extension)
        checkpoint(data)
        cache = SCRATCH / 'empty-pycache'
        cache.mkdir(exist_ok=True)
        if any(cache.iterdir()):
            raise ValueError('pycache prefix is not empty')
        env = os.environ.copy()
        for key in tuple(env):
            if key in ('PYTHONPATH', 'PYTHONPYCACHEPREFIX') or key.startswith('DYLD_'):
                env.pop(key)
        env.update(PYTHONHASHSEED='1', PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', PYTHONPYCACHEPREFIX=str(cache))
        data['recipe']['environment'] = {key: env[key] for key in ('PYTHONHASHSEED', 'PYTHONNOUSERSITE', 'PYTHONDONTWRITEBYTECODE')}
        for side in ('pure', 'guard'):
            child_env = env | {'PYTHONPATH': str(overlays[side])}
            command = [str(BASE / 'bin/python3.16'), '-S', '-B', '-c',
                       'import ipaddress, sys; print(ipaddress.__file__); print(getattr(sys.modules.get("_rust_ipv4_scan"), "__file__", "absent"))']
            record = measure(command, child_env, f'probe-{side}', 'probe')
            data['attempts'].append(record)
            checkpoint(data)
            expected = f'{overlays[side] / "ipaddress.py"}\nabsent'
            if record.get('failure') or record.get('output') != expected:
                raise RuntimeError(f'{side} overlay probe failed')
        for family, count in (('pure-self', 2), ('guard-self', 2), ('comparison', 5)):
            for pair in range(1, count + 1):
                sides = ('pure', 'pure') if family == 'pure-self' else ('guard', 'guard') if family == 'guard-self' else ('pure', 'guard') if pair % 2 else ('guard', 'pure')
                group = {'family': family, 'pair': pair, 'order': sides, 'host_before': host(), 'attempts': []}
                data['pairs'].append(group)
                checkpoint(data)
                for position, side in enumerate(sides, 1):
                    child_env = env | {'PYTHONPATH': str(overlays[side])}
                    command = [str(BASE / 'bin/python3.16'), '-S', '-B', str(WORKLOAD), '--count', '30000', '--rounds', '2']
                    record = measure(command, child_env, f'{family}-{pair:02d}-{position:02d}-{side}', 'workload')
                    record['side'] = side
                    data['attempts'].append(record)
                    group['attempts'].append(record['id'])
                    checkpoint(data)
                    if record.get('failure'):
                        raise RuntimeError(f'{record["id"]} failed')
                group['host_after'] = host()
                checkpoint(data)
        data['summary'] = {}
        by_id = {record['id']: record for record in data['attempts']}
        for family in ('pure-self', 'guard-self', 'comparison'):
            pairs = [group for group in data['pairs'] if group['family'] == family]
            for metric in ('wall_seconds', 'cpu_seconds'):
                ratios = []
                for group in pairs:
                    first, second = (by_id[name] for name in group['attempts'])
                    for record in (first, second):
                        record['cpu_seconds'] = record['user_seconds'] + record['system_seconds']
                    a, b = ((second, first) if family != 'comparison' else
                            (next(r for r in (first, second) if r['side'] == 'guard'),
                             next(r for r in (first, second) if r['side'] == 'pure')))
                    ratios.append(a[metric] / b[metric])
                data['summary'].setdefault(family, {})[metric] = {'ratios': ratios, 'median': statistics.median(ratios), 'range': [min(ratios), max(ratios)]}
        checkpoint(data)
    except Exception as error:
        data['failure'] = repr(error)
        checkpoint(data)
        raise
    finally:
        data['host_after'] = host()
        checkpoint(data)


def followup(source_evidence, evidence_path, scratch_path):
    global EVIDENCE, SCRATCH
    SCRATCH = scratch_path
    data = json.loads(source_evidence.read_text())
    if 'followup' in data:
        raise ValueError('follow-up already exists')
    EVIDENCE = evidence_path
    reserve_evidence(EVIDENCE)
    follow = {'attempts': [], 'memory_pairs': [], 'host_before': host(),
              'measurement': '/usr/bin/time -l -p child resource fields for compiler process trees and workload physical footprint'}
    data['followup'] = follow
    checkpoint(data)
    overlays = {side: SCRATCH / side for side in ('pure', 'guard')}
    env = os.environ.copy()
    for key in tuple(env):
        if key in ('PYTHONPATH', 'PYTHONPYCACHEPREFIX') or key.startswith('DYLD_'):
            env.pop(key)
    env.update(PYTHONHASHSEED='1', PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1',
               PYTHONPYCACHEPREFIX=str(SCRATCH / 'empty-pycache'))
    native = SCRATCH / 'native'
    archive = native / 'libipv4_scan-timed.a'
    extension = native / '_rust_ipv4_scan-timed.so'
    compiler_commands = data['recipe']['compiler_commands']
    timed_commands = [compiler_commands[0][:-1] + [str(archive)],
                      compiler_commands[1][:-3] + [str(archive), '-o', str(extension)]]
    try:
        for index, command in enumerate(timed_commands, 1):
            item = timed(command, os.environ.copy(), f'compiler-tree-{index:02d}', workload=False)
            follow['attempts'].append(item)
            checkpoint(data)
            if item.get('failure'):
                raise RuntimeError(f'timed compiler step {index} failed')
        follow['timed_compiler_commands'] = timed_commands
        follow['timed_archive_sha256'] = sha(archive)
        follow['timed_extension_sha256'] = sha(extension)
        checkpoint(data)
        for side in ('pure', 'guard'):
            child_env = env | {'PYTHONPATH': str(overlays[side])}
            probe = [str(BASE / 'bin/python3.16'), '-S', '-B', '-c',
                     'import ipaddress,sys; ipaddress.IPv4Address("1.2.3.4"); print(ipaddress.__file__); print(getattr(sys.modules.get("_rust_ipv4_scan"), "__file__", "absent"))']
            item = timed(probe, child_env, f'extension-use-{side}', workload=False)
            follow['attempts'].append(item)
            checkpoint(data)
            expected = f'{overlays[side] / "ipaddress.py"}\n{overlays["guard"] / "_rust_ipv4_scan.cpython-316-darwin.so" if side == "guard" else "absent"}'
            if item.get('failure') or item.get('output') != expected:
                raise RuntimeError(f'{side} extension use probe failed: {item.get("output")}')
        for pair in range(1, 4):
            sides = ('pure', 'guard') if pair % 2 else ('guard', 'pure')
            group = {'pair': pair, 'order': sides, 'host_before': host(), 'attempts': []}
            follow['memory_pairs'].append(group)
            checkpoint(data)
            for position, side in enumerate(sides, 1):
                child_env = env | {'PYTHONPATH': str(overlays[side])}
                command = [str(BASE / 'bin/python3.16'), '-S', '-B', str(WORKLOAD), '--count', '30000', '--rounds', '2']
                item = timed(command, child_env, f'memory-{pair:02d}-{position:02d}-{side}', workload=True)
                item['side'] = side
                follow['attempts'].append(item)
                group['attempts'].append(item['id'])
                checkpoint(data)
                if item.get('failure'):
                    raise RuntimeError(f'{item["id"]} failed')
            group['host_after'] = host()
            checkpoint(data)
        by_id = {item['id']: item for item in follow['attempts']}
        deltas = []
        for group in follow['memory_pairs']:
            sides = {by_id[name]['side']: by_id[name] for name in group['attempts']}
            deltas.append(sides['guard']['peak_footprint_bytes'] - sides['pure']['peak_footprint_bytes'])
        follow['footprint_delta_bytes'] = deltas
        follow['median_footprint_delta_bytes'] = statistics.median(deltas)
        checkpoint(data)
    except Exception as error:
        follow['failure'] = repr(error)
        checkpoint(data)
        raise
    finally:
        follow['host_after'] = host()
        checkpoint(data)


def timed(command, env, attempt_id, workload):
    out = SCRATCH / f'{attempt_id}.stdout'
    err = SCRATCH / f'{attempt_id}.stderr'
    started = time.perf_counter()
    with out.open('wb') as stdout, err.open('wb') as stderr:
        child = subprocess.Popen(['/usr/bin/time', '-l', '-p', *command], env=env,
                                 stdout=stdout, stderr=stderr)
        _, status, usage = os.wait4(child.pid, 0)
    stderr_text = err.read_text(errors='replace')
    stdout_text = out.read_text(errors='replace')
    out.unlink()
    err.unlink()
    record = {'id': attempt_id, 'returncode': os.waitstatus_to_exitcode(status),
              'wall_seconds': time.perf_counter() - started,
              'wrapper_user_seconds': usage.ru_utime,
              'wrapper_system_seconds': usage.ru_stime,
              'wrapper_peak_rss_bytes': usage.ru_maxrss,
              'wrapper_swaps': usage.ru_nswap,
              'process_count': 'one direct child; compiler subprocesses included by time'}
    for label, key, cast in (('user', 'user_seconds', float), ('sys', 'system_seconds', float),
                             ('maximum resident set size', 'peak_rss_bytes', int),
                             ('peak memory footprint', 'peak_footprint_bytes', int),
                             ('swaps', 'swaps', int)):
        pattern = (r'^' + re.escape(label) + r' ([\d.]+)$' if label in ('user', 'sys')
                   else r'^\s*(\d+)\s+' + re.escape(label) + r'$')
        match = re.search(pattern, stderr_text, re.M)
        if match:
            record[key] = cast(match.group(1))
    if record['returncode'] or any(key not in record for key in
                                   ('user_seconds', 'system_seconds', 'peak_rss_bytes',
                                    'peak_footprint_bytes', 'swaps')):
        record['failure'] = {'stdout_tail': stdout_text[-500:],
                             'stderr_tail': stderr_text[-1000:]}
    elif workload:
        try:
            output = json.loads(stdout_text)
            record['output'] = output
            if output.get('digest') != EXPECTED_DIGEST or output.get('count') != 30000 or output.get('rounds') != 2:
                record['failure'] = 'workload output identity differs'
        except json.JSONDecodeError:
            record['failure'] = 'invalid workload JSON: ' + stdout_text[-300:]
    else:
        record['output'] = stdout_text.strip()
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--followup', action='store_true')
    parser.add_argument('--source-evidence', type=Path, default=DATA,
                        help='earlier evidence used by --followup')
    parser.add_argument('--evidence', type=Path,
                        help='unique JSON output path for this run')
    parser.add_argument('--scratch', type=Path, default=SCRATCH,
                        help='unique scratch path for a new run, or earlier scratch for --followup')
    args = parser.parse_args()
    if args.followup:
        followup(args.source_evidence, args.evidence or DATA.with_name(DATA.stem + '-followup.json'),
                 args.scratch)
    else:
        main(args.evidence or DATA, args.scratch)
