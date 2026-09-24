"""Diagnostic SequenceMatcher dictionary-reuse probe; no product patch."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import textwrap
import time


_ORIGINAL = difflib.SequenceMatcher.find_longest_match
_WORKLOAD = Path(__file__).resolve().parents[2] / 'benchmarks/workloads/difflib.py'


def install_candidate() -> None:
    # Keep the pinned CPython implementation intact except for reusing the
    # previous row's dictionary. Assert the source shape so this fails closed.
    source = textwrap.dedent(inspect.getsource(_ORIGINAL))
    edits = (
        ('    nothing = []\n', '    nothing = []\n    spare_j2len = {}\n'),
        ('        newj2len = {}\n',
         '        newj2len = spare_j2len\n        newj2len.clear()\n'),
        ('        j2len = newj2len\n',
         '        spare_j2len, j2len = j2len, newj2len\n'),
    )
    for old, new in edits:
        if source.count(old) != 1:
            raise RuntimeError(f'pinned difflib source changed: {old!r}')
        source = source.replace(old, new)
    namespace = {'Match': difflib.Match}
    exec(compile(source, difflib.__file__, 'exec'), namespace)
    difflib.SequenceMatcher.find_longest_match = namespace['find_longest_match']


def snapshot(a, b, *, isjunk=None, autojunk=True, mutate=None, matcher_type=difflib.SequenceMatcher):
    matcher = matcher_type(isjunk, a, b, autojunk=autojunk)
    if mutate:
        mutate(matcher)
    return (matcher.find_longest_match(), matcher.get_matching_blocks(),
            matcher.get_opcodes(), list(matcher.get_grouped_opcodes()),
            matcher.ratio(), matcher.quick_ratio())


def cases():
    rng = random.Random(160924)
    yield ('empty', (), (), {})
    yield ('prefix counterexample', list('ab'), list('acab'), {})
    yield ('tie', list('ababxxabab'), list('bababyybab'), {})
    yield ('popular 199', ['x'] * 199 + ['a'], ['x'] * 199 + ['b'], {})
    yield ('popular 200', ['x'] * 200 + ['a'], ['x'] * 200 + ['b'], {})
    yield ('autojunk off', ['x'] * 220 + ['a'], ['x'] * 220 + ['b'], {'autojunk': False})
    yield ('junk', list(' a b c '), list(' a x b c '), {'isjunk': lambda x: x == ' '})
    yield ('nonstring', [(i % 7, i % 3) for i in range(70)],
           [(i % 7, i % 3) for i in range(10, 80)], {})
    yield ('b2j mutation', list('abcabc'), list('abcabc'),
           {'mutate': lambda m: m.b2j.clear()})
    yield ('bjunk mutation', list('a a'), list('a a'),
           {'mutate': lambda m: m.bjunk.add('a')})
    yield ('bpopular mutation', ['a'] * 210, ['a'] * 210,
           {'mutate': lambda m: m.bpopular.clear()})
    class Matcher(difflib.SequenceMatcher):
        pass
    yield ('subclass', list('abc'), list('acb'), {'matcher_type': Matcher})
    for index in range(120):
        a = [rng.randrange(11) for _ in range(rng.randrange(0, 65))]
        b = [rng.randrange(11) for _ in range(rng.randrange(0, 65))]
        yield (f'random {index}', a, b, {'autojunk': bool(index % 2)})


def check() -> None:
    inputs = list(cases())
    expected = [(name, snapshot(a, b, **kwargs)) for name, a, b, kwargs in inputs]
    public = []
    for name, a, b, _ in inputs:
        if all(isinstance(item, str) for item in a + b):
            difflib.HtmlDiff._default_prefix = 0
            public.append((name,
                ''.join(difflib.unified_diff(a, b)),
                ''.join(difflib.context_diff(a, b)),
                list(difflib.Differ().compare(a, b)),
                difflib.HtmlDiff().make_table(a, b)))
    install_candidate()
    for (name, prior), (_, a, b, kwargs) in zip(expected, inputs):
        current = snapshot(a, b, **kwargs)
        if current != prior:
            raise AssertionError(f'matcher mismatch: {name}: {prior!r} != {current!r}')
    for name, a, b, _ in inputs:
        if all(isinstance(item, str) for item in a + b):
            difflib.HtmlDiff._default_prefix = 0
            current = (name, ''.join(difflib.unified_diff(a, b)),
                       ''.join(difflib.context_diff(a, b)),
                       list(difflib.Differ().compare(a, b)),
                       difflib.HtmlDiff().make_table(a, b))
            if current != public.pop(0):
                raise AssertionError(f'public diff mismatch: {name}')
    print(json.dumps({'matched_cases': len(inputs), 'public_cases': sum(all(isinstance(x, str) for x in a + b) for _, a, b, _ in inputs),
                      'source_sha256': hashlib.sha256(Path(difflib.__file__).read_bytes()).hexdigest()}))


def workload(scenario: str, iterations: int, candidate: bool) -> None:
    spec = importlib.util.spec_from_file_location('difflib_workload', _WORKLOAD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if candidate:
        install_candidate()
    result = module._SCENARIOS[scenario](iterations)
    print(json.dumps(result, sort_keys=True))


def pair(scenario: str, iterations: int, repeats: int) -> None:
    records = []
    for repeat in range(repeats):
        for candidate in ((False, True) if repeat % 2 == 0 else (True, False)):
            command = [sys.executable, __file__, 'workload', scenario,
                       str(iterations), 'candidate' if candidate else 'control']
            start = time.monotonic()
            process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
            pid, status, usage = os.wait4(process.pid, 0)
            output = process.stdout.read()
            error = process.stderr.read()
            elapsed = time.monotonic() - start
            if pid != process.pid or status:
                raise RuntimeError(error.decode())
            result = json.loads(output)
            records.append({'repeat': repeat, 'mode': 'candidate' if candidate else 'control',
                            'external_wall_per_diff': elapsed / iterations,
                            'internal_wall_per_diff': result['elapsed_seconds'] / iterations,
                            'user_cpu_per_diff': usage.ru_utime / iterations,
                            'system_cpu_per_diff': usage.ru_stime / iterations,
                            'peak_rss_bytes': usage.ru_maxrss,
                            'digest': result['digest']})
    print(json.dumps({'scenario': scenario, 'iterations': iterations,
                      'loadavg': os.getloadavg(), 'records': records}, indent=2))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('check')
    work = sub.add_parser('workload')
    work.add_argument('scenario')
    work.add_argument('iterations', type=int)
    work.add_argument('mode', choices=('control', 'candidate'))
    pair_parser = sub.add_parser('pair')
    pair_parser.add_argument('scenario')
    pair_parser.add_argument('iterations', type=int)
    pair_parser.add_argument('repeats', type=int)
    args = parser.parse_args()
    if args.action == 'check':
        check()
    elif args.action == 'workload':
        workload(args.scenario, args.iterations, args.mode == 'candidate')
    else:
        pair(args.scenario, args.iterations, args.repeats)


if __name__ == '__main__':
    main()
