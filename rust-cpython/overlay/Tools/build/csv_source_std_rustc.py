"""Record fresh compiler units and select the CSV source runtime for target code."""
import os
import sys

if __name__ == '__main__':
    from csv_source_std_bootstrap import configure_bootstrap_path
    configure_bootstrap_path()

import hashlib
import json
from pathlib import Path
import signal
import subprocess
import time


def publish_receipt(path, row):
    # A killed wrapper must leave either the previous complete state or the new
    # complete state visible to the recipe's independent compiler cleanup.
    pending = path.with_suffix('.pending')
    pending.write_text(json.dumps(row, indent=2) + '\n')
    os.replace(pending, path)


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from csv_source_std import artifact, digest, host_capability_probe, is_query, jobserver_fds, target_arguments
    config_path = Path(os.environ['CSV_SOURCE_STD_RUSTC_CONFIG'])
    config = json.loads(config_path.read_text())
    compiler = Path(config['rustc'])
    if digest(compiler) != config['rustc_sha256']:
        raise ValueError('source std compiler identity changed')
    args = sys.argv[1:]
    original = list(args)
    query = is_query(args)
    target = Path(config['target_directory']).resolve()
    outputs = [args[i + 1] for i, value in enumerate(args[:-1]) if value in ('--out-dir', '-o')]
    if not query and (not outputs or any(not Path(raw).resolve().is_relative_to(target) for raw in outputs)):
        raise ValueError('compiler output outside fresh owned target')
    if any(arg.startswith('@') for arg in args):
        raise ValueError('compiler response files are not admitted')
    sources = [Path(raw).resolve() for raw in args if raw.endswith('.rs')]
    for source in sources:
        if str(source) in config['source_files']:
            if digest(source) != config['source_files'][str(source)]:
                raise ValueError('compiler source changed')
        elif not source.is_relative_to(target):
            raise ValueError('compiler source outside frozen inputs/generated target')
    probe = host_capability_probe(args, os.environ, os.getcwd(), config['source_files'], target)
    if config['runtime_pairs'] and not probe and not query:
        args = target_arguments(args, config['runtime_pairs'], config['runtime_directories'], config['target_sysroot'])
    row = {'argv': [str(compiler), *args], 'original_argv': [str(compiler), *original],
           'cwd': os.getcwd(), 'environment': dict(os.environ), 'query': query,
           'source_files': {str(p): digest(p) for p in sources}, 'state': 'running',
           'role': 'host_capability_probe' if probe else ('compiler_query' if query else 'compiler_unit')}
    if '--crate-name' in args and args[args.index('--crate-name') + 1] == 'cpython_sys' and not query:
        generated = Path(os.environ['OUT_DIR']).resolve() / 'c_api.rs'
        if not generated.is_relative_to(target):
            raise ValueError('generated C API source outside owned target')
        row['generated_c_api_before_compile'] = artifact(generated)
    receipts = Path(config['receipts'])
    receipts.mkdir(parents=True, exist_ok=True)
    receipt = receipts / (str(os.getpid()) + '.json')
    process = subprocess.Popen([str(compiler), *args], start_new_session=True,
                               pass_fds=jobserver_fds(os.environ.get('CARGO_MAKEFLAGS', '')))
    try:
        row.update(pid=process.pid, pgid=os.getpgid(process.pid), started_ns=time.time_ns())
        publish_receipt(receipt, row)
        row['exit_code'] = process.wait(timeout=180)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            row['killed'] = True
        row.update(reaped_exit=process.wait(), state='reaped', completed_ns=time.time_ns())
        # Cargo can share an output directory with concurrent work. These files
        # are observations; the recipe rehashes final dependency inputs after
        # the complete Cargo process exits before using them for producer replay.
        row['output_locations'] = outputs
        publish_receipt(receipt, row)
    return row['exit_code']


if __name__ == '__main__':
    sys.exit(main())
