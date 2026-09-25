"""Record serial paired complete routing workloads with kernel resources."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
CONTROL = Path('/Users/josh/d/python-build-exp-tar-helper-guard-20260925/rust-cpython/stage-tar-guard')
CANDIDATE = ROOT / 'rust-cpython/stage-ipv4-scan'
GUARD = ROOT / 'rust-cpython/stage-ipv4-guard'
WORKLOAD = ROOT / 'rust-cpython/experiments/ipaddress_v4_workload.py'
DATA = ROOT / 'rust-cpython/experiments/data/ipaddress-v4-scan-20260925.json'
TIMING = re.compile(r'^real ([\d.]+)\nuser ([\d.]+)\nsys ([\d.]+)$', re.M)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def field(stderr, label):
    match = re.search(r'^\s*(\d+)\s+' + re.escape(label) + r'$', stderr, re.M)
    if match is None:
        raise ValueError(f'missing kernel field {label}')
    return int(match.group(1))


def attempt(pair, position, side, env, family='comparison', kind='routing'):
    stage = {'control': CONTROL, 'candidate': CANDIDATE, 'guard': GUARD}[side]
    executable = stage / 'bin/python3.16'
    command = ([str(executable), '-S', '-B', '-c', 'import ipaddress']
               if kind == 'cold-import' else
               [str(executable), '-B', str(WORKLOAD), '--count', '30000', '--rounds', '2'])
    started = time.perf_counter()
    result = subprocess.run(['/usr/bin/time', '-l', '-p', *command],
                            capture_output=True, text=True, env=env)
    wall = time.perf_counter() - started
    record = {'id': f'{family}-{pair:02d}-{position:02d}-{side}',
              'kind': kind, 'family': family, 'pair': pair,
              'position': position, 'side': side,
              'returncode': result.returncode, 'wall_seconds': wall}
    match = TIMING.search(result.stderr)
    if match is not None:
        record.update(kernel_real_seconds=float(match.group(1)),
                      user_seconds=float(match.group(2)),
                      system_seconds=float(match.group(3)),
                      peak_rss_bytes=field(result.stderr, 'maximum resident set size'),
                      peak_footprint_bytes=field(result.stderr, 'peak memory footprint'),
                      swaps=field(result.stderr, 'swaps'))
    if result.returncode == 0 and kind == 'cold-import':
        record['output'] = {'imported': result.stdout == ''}
    elif result.returncode == 0:
        try:
            record['output'] = json.loads(result.stdout)
        except json.JSONDecodeError:
            record['failure'] = {'reason': 'invalid output JSON', 'stdout': result.stdout[-1000:]}
    else:
        record['failure'] = {'stdout': result.stdout[-1000:],
                             'stderr': result.stderr[-1500:]}
    return record


def main():
    if DATA.exists():
        raise FileExistsError(DATA)
    env = os.environ.copy()
    for key in tuple(env):
        if key in ('PYTHONPATH', 'PYTHONPYCACHEPREFIX') or key.startswith('DYLD_'):
            env.pop(key)
    cache = ROOT / 'rust-cpython/work/ipaddress-v4/empty-pycache'
    cache.mkdir(parents=True, exist_ok=True)
    if any(cache.iterdir()):
        raise ValueError('measurement pycache prefix must be empty')
    env.update(PYTHONHASHSEED='1', PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1',
               PYTHONPYCACHEPREFIX=str(cache))
    evidence = {
        'recipe': {
            'workload': 'ipaddress_v4_workload.py --count 30000 --rounds 2',
            'workload_sha256': sha256(WORKLOAD),
            'control_interpreter_sha256': sha256(CONTROL / 'bin/python3.16'),
            'candidate_interpreter_sha256': sha256(CANDIDATE / 'bin/python3.16'),
            'control_ipaddress_sha256': sha256(CONTROL / 'lib/python3.16/ipaddress.py'),
            'candidate_ipaddress_sha256': sha256(CANDIDATE / 'lib/python3.16/ipaddress.py'),
            'measurement': '/usr/bin/time -l -p around each direct Python process; perf_counter around the time process',
            'cache_policy': 'empty PYTHONPYCACHEPREFIX and PYTHONDONTWRITEBYTECODE=1; both arms import source',
            'environment': {key: env[key] for key in ('PYTHONHASHSEED', 'PYTHONNOUSERSITE', 'PYTHONDONTWRITEBYTECODE')},
        },
        'host_swap_before': subprocess.check_output(['sysctl', 'vm.swapusage'], text=True).strip(),
        'host_load_before': subprocess.check_output(['uptime'], text=True).strip(),
        'attempts': [], 'pairs': [],
    }
    try:
        output = None
        for family, count in (('self', 3), ('comparison', 5)):
            for number in range(1, count + 1):
                sides = (('control', 'control') if family == 'self' else
                         ('control', 'candidate') if number % 2 else
                         ('candidate', 'control'))
                ids = []
                for position, side in enumerate(sides, 1):
                    record = attempt(number, position, side, env, family)
                    evidence['attempts'].append(record)
                    ids.append(record['id'])
                    if record['returncode'] or 'failure' in record or 'user_seconds' not in record:
                        raise ValueError(f'failed attempt {record["id"]}')
                    if output is None:
                        output = record['output']
                    elif record['output'] != output:
                        record['failure'] = {'reason': 'public output differs from first control'}
                        raise ValueError(f'output mismatch {record["id"]}')
                evidence['pairs'].append({'family': family, 'number': number,
                                          'order': sides, 'attempts': ids})
    finally:
        evidence['host_swap_after'] = subprocess.check_output(['sysctl', 'vm.swapusage'], text=True).strip()
        evidence['host_load_after'] = subprocess.check_output(['uptime'], text=True).strip()
        DATA.write_text(json.dumps(evidence, indent=2, sort_keys=True) + '\n')


def calibrate():
    evidence = json.loads(DATA.read_text())
    env = os.environ.copy()
    for key in tuple(env):
        if key in ('PYTHONPATH', 'PYTHONPYCACHEPREFIX') or key.startswith('DYLD_'):
            env.pop(key)
    env.update(PYTHONHASHSEED='1', PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1',
               PYTHONPYCACHEPREFIX=str(ROOT / 'rust-cpython/work/ipaddress-v4/empty-pycache'))
    evidence['calibration_order'] = 'three control/control pairs after five comparison pairs'
    try:
        for number in range(1, 4):
            ids = []
            for position in (1, 2):
                record = attempt(number, position, 'control', env)
                record['id'] = f'self-{number:02d}-{position:02d}-control'
                evidence['attempts'].append(record)
                ids.append(record['id'])
                if (record['returncode'] or 'failure' in record or
                        record.get('output') != evidence['attempts'][0]['output']):
                    raise ValueError(f'failed calibration {record["id"]}')
            evidence['pairs'].append({'family': 'self', 'number': number,
                                      'order': ('control', 'control'), 'attempts': ids})
    finally:
        evidence['host_swap_after_calibration'] = subprocess.check_output(
            ['sysctl', 'vm.swapusage'], text=True).strip()
        evidence['host_load_after_calibration'] = subprocess.check_output(
            ['uptime'], text=True).strip()
        DATA.write_text(json.dumps(evidence, indent=2, sort_keys=True) + '\n')


def guard_followup():
    evidence = json.loads(DATA.read_text())
    if 'guard_followup' in evidence:
        raise ValueError('guard follow-up already recorded')
    env = os.environ.copy()
    for key in tuple(env):
        if key in ('PYTHONPATH', 'PYTHONPYCACHEPREFIX') or key.startswith('DYLD_'):
            env.pop(key)
    cache = ROOT / 'rust-cpython/work/ipaddress-v4/empty-guard-pycache'
    cache.mkdir(parents=True, exist_ok=True)
    if any(cache.iterdir()):
        raise ValueError('guard measurement pycache prefix must be empty')
    env.update(PYTHONHASHSEED='1', PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1',
               PYTHONPYCACHEPREFIX=str(cache))
    followup = {
        'recipe': {
            'workload': 'ipaddress_v4_workload.py --count 30000 --rounds 2',
            'workload_sha256': sha256(WORKLOAD),
            'control_interpreter_sha256': sha256(CONTROL / 'bin/python3.16'),
            'prior_interpreter_sha256': sha256(CANDIDATE / 'bin/python3.16'),
            'guard_interpreter_sha256': sha256(GUARD / 'bin/python3.16'),
            'control_ipaddress_sha256': sha256(CONTROL / 'lib/python3.16/ipaddress.py'),
            'prior_ipaddress_sha256': sha256(CANDIDATE / 'lib/python3.16/ipaddress.py'),
            'guard_ipaddress_sha256': sha256(GUARD / 'lib/python3.16/ipaddress.py'),
            'measurement': '/usr/bin/time -l -p around each direct Python process; perf_counter around the time process',
            'cache_policy': 'empty PYTHONPYCACHEPREFIX and PYTHONDONTWRITEBYTECODE=1; all arms import source',
            'environment': {key: env[key] for key in ('PYTHONHASHSEED', 'PYTHONNOUSERSITE', 'PYTHONDONTWRITEBYTECODE')},
        },
        'host_swap_before': subprocess.check_output(['sysctl', 'vm.swapusage'], text=True).strip(),
        'host_load_before': subprocess.check_output(['uptime'], text=True).strip(),
        'attempts': [], 'pairs': [],
    }
    expected = evidence['attempts'][0]['output']
    plan = (('guard-self', 'routing', 3, ('candidate', 'candidate')),
            ('guard-prior', 'routing', 5, ('candidate', 'guard')),
            ('guard-public', 'routing', 5, ('control', 'guard')),
            ('guard-cold', 'cold-import', 5, ('candidate', 'guard')))
    try:
        for family, kind, count, base_sides in plan:
            for number in range(1, count + 1):
                sides = base_sides if number % 2 else tuple(reversed(base_sides))
                ids = []
                for position, side in enumerate(sides, 1):
                    record = attempt(number, position, side, env, family, kind)
                    followup['attempts'].append(record)
                    ids.append(record['id'])
                    if (record['returncode'] or 'failure' in record or
                            'user_seconds' not in record or
                            record.get('output') != (expected if kind == 'routing'
                                                     else {'imported': True})):
                        record['failure'] = {'reason': 'command, resource, or output mismatch',
                                             'stderr_tail': record.get('failure', {}).get('stderr', '')}
                        raise ValueError(f'failed follow-up attempt {record["id"]}')
                followup['pairs'].append({'family': family, 'kind': kind,
                                          'number': number, 'order': sides,
                                          'attempts': ids})
    finally:
        followup['host_swap_after'] = subprocess.check_output(
            ['sysctl', 'vm.swapusage'], text=True).strip()
        followup['host_load_after'] = subprocess.check_output(
            ['uptime'], text=True).strip()
        evidence['guard_followup'] = followup
        DATA.write_text(json.dumps(evidence, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    if sys.argv[1:] == ['--guard-followup']:
        guard_followup()
    elif sys.argv[1:] == ['--self-calibrate']:
        calibrate()
    else:
        main()
