"""Record paired complete TAR reads and cold imports for the helper guard."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
CONTROL = Path('/Users/josh/d/python-build-exp-tar-owned-module-20260925/rust-cpython/stage-tar-owned/bin/python3.16')
CANDIDATE = ROOT / 'rust-cpython/stage-tar-guard/bin/python3.16'
QUOTE_ONLY = Path('/Users/josh/d/python-build-exp-merged-macos-url-20260925/rust-cpython/stage-quote-only/bin/python3.16')
ARCHIVE = ROOT / '.cache/objects/965dbc9c847b0ed779a16134495b8690c9fc957996d8bcbb83c47089d4e81467.blob'
WORKLOAD = ROOT / 'rust-cpython/experiments/source_tar_hybrid.py'
DATA = ROOT / 'rust-cpython/experiments/data/tar-helper-guard-20260925.json'
TIMING = re.compile(r'^real ([\d.]+)\nuser ([\d.]+)\nsys ([\d.]+)$', re.M)
EXPECTED = '4274d870abacbefea6bbdb2175de8b4073198e1fd39f34ede1c065b3faf1a805'


def kernel_field(raw, label):
    match = re.search(r'^\s*(\d+)\s+' + re.escape(label) + r'$', raw, re.M)
    if match is None:
        raise ValueError(f'missing {label}')
    return int(match.group(1))


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def attempt(kind, family, number, position, side, env):
    executable = {'control': CONTROL, 'candidate': CANDIDATE, 'quote-only': QUOTE_ONLY}[side]
    command = [str(executable), str(WORKLOAD), str(ARCHIVE), '--loops', '3']
    if kind == 'cold-import':
        command = [str(executable), '-S', '-c', 'import tarfile']
    started = time.perf_counter()
    result = subprocess.run(['/usr/bin/time', '-l', '-p', *command],
                            capture_output=True, text=True, env=env)
    wall = time.perf_counter() - started
    match = TIMING.search(result.stderr)
    record = {'id': f'{kind}-{family}-{number:02d}-{position:02d}-{side}',
              'kind': kind, 'family': family, 'pair': number, 'position': position,
              'side': side, 'returncode': result.returncode,
              'external_wall_seconds': wall}
    if match is None:
        record['timing_failure'] = result.stderr[-1000:]
        return record
    record.update(kernel_real_seconds=float(match.group(1)),
                  user_seconds=float(match.group(2)),
                  system_seconds=float(match.group(3)),
                  peak_rss_bytes=kernel_field(result.stderr, 'maximum resident set size'),
                  peak_footprint_bytes=kernel_field(result.stderr, 'peak memory footprint'),
                  swaps=kernel_field(result.stderr, 'swaps'))
    if result.returncode:
        record['failure'] = {'stdout': result.stdout[-1000:],
                             'stderr': result.stderr[-1000:]}
        return record
    if kind == 'archive':
        try:
            output = json.loads(result.stdout)
            if (output['digest'], output['members'], output['regular_files'],
                    output['regular_bytes'], output['loops']) != (
                    EXPECTED, 6539, 6031, 136064031, 3):
                raise ValueError('archive output differs from the locked workload')
            record['output'] = output
        except (ValueError, KeyError) as error:
            record['failure'] = {'reason': str(error), 'stdout': result.stdout[-1000:]}
    return record


def main():
    if DATA.exists():
        raise FileExistsError(DATA)
    calibration = ROOT / 'rust-cpython/work/guard-discarded-calibration.json'
    prior = json.loads(calibration.read_text()) if calibration.exists() else None
    env = os.environ.copy()
    for key in tuple(env):
        if key in ('PYTHONPATH', 'PYTHONPYCACHEPREFIX') or key.startswith('DYLD_'):
            env.pop(key)
    cache = ROOT / 'rust-cpython/work/guard-measure-empty-pycache'
    cache.mkdir(parents=True, exist_ok=True)
    if any(cache.iterdir()):
        raise ValueError('measurement pycache prefix is not empty')
    env.update(PYTHONHASHSEED='1', PYTHONNOUSERSITE='1', PYTHONMALLOC='default',
               PYTHONDONTWRITEBYTECODE='1', PYTHONPYCACHEPREFIX=str(cache))
    evidence = {
        'recipe': {'workload': 'source_tar_hybrid.py --loops 3; 6539 members, 6031 files, 408192093 logical bytes per process',
                   'archive_sha256': sha256(ARCHIVE), 'cache_policy': 'empty PYTHONPYCACHEPREFIX, PYTHONDONTWRITEBYTECODE=1, source imports',
                   'environment': {key: env[key] for key in ('PYTHONHASHSEED', 'PYTHONNOUSERSITE', 'PYTHONMALLOC', 'PYTHONDONTWRITEBYTECODE')},
                   'measurement': '/usr/bin/time -l -p around direct Python child; external perf_counter; no sampler during timing',
                   'control_interpreter_sha256': sha256(CONTROL),
                   'candidate_interpreter_sha256': sha256(CANDIDATE),
                   'control_tarfile_sha256': sha256(CONTROL.parents[1] / 'lib/python3.16/tarfile.py'),
                   'candidate_tarfile_sha256': sha256(CANDIDATE.parents[1] / 'lib/python3.16/tarfile.py')},
        'host_swap_before': subprocess.check_output(['sysctl', 'vm.swapusage'], text=True).strip(),
        'host_load_before': subprocess.check_output(['uptime'], text=True).strip(),
        'attempts': [], 'pairs': []}
    if prior is not None:
        evidence['discarded_calibration'] = {
            'reason': 'time -l -p parser expected the one-line -l format; raw stderr was not retained, so kernel CPU and memory counters cannot be recovered',
            'attempts': prior['attempts'], 'pairs': prior['pairs']}
    try:
        for kind in ('archive', 'cold-import'):
            families = ('self', 'comparison') if kind == 'archive' else ('comparison',)
            for family in families:
                for number in range(1, 6 if family == 'comparison' else 4):
                    sides = ('control', 'control') if family == 'self' else ('control', 'candidate')
                    if number % 2 == 0:
                        sides = tuple(reversed(sides))
                    ids = []
                    for position, side in enumerate(sides, 1):
                        record = attempt(kind, family, number, position, side, env)
                        evidence['attempts'].append(record)
                        if 'user_seconds' not in record or record.get('failure'):
                            raise ValueError(f'failed measurement: {record["id"]}')
                        ids.append(record['id'])
                    evidence['pairs'].append({'kind': kind, 'family': family, 'number': number, 'attempts': ids})
        public = {'quote_interpreter_sha256': sha256(QUOTE_ONLY),
                  'quote_tarfile_sha256': sha256(QUOTE_ONLY.parents[1] / 'lib/python3.16/tarfile.py'),
                  'host_load_before': subprocess.check_output(['uptime'], text=True).strip(),
                  'attempts': [], 'pairs': []}
        evidence['public_benefit'] = public
        for number in range(1, 6):
            sides = ('quote-only', 'candidate') if number % 2 else ('candidate', 'quote-only')
            ids = []
            for position, side in enumerate(sides, 1):
                record = attempt('archive', 'public-benefit', number, position, side, env)
                public['attempts'].append(record)
                if 'user_seconds' not in record or record.get('failure'):
                    raise ValueError(f'failed measurement: {record["id"]}')
                ids.append(record['id'])
            public['pairs'].append({'number': number, 'attempts': ids})
        public['host_load_after'] = subprocess.check_output(['uptime'], text=True).strip()
    finally:
        evidence['host_swap_after'] = subprocess.check_output(['sysctl', 'vm.swapusage'], text=True).strip()
        evidence['host_load_after'] = subprocess.check_output(['uptime'], text=True).strip()
        DATA.write_text(json.dumps(evidence, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
