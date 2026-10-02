"""Generate module rules without compiling or loading an extension."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ORIGINAL_SHA256 = 'eda7fcb9f1b192fb558b134531af1697fbf65a2724695a3f4b59cfdddf9a4117'
OPTIONS = None


def invoke(arguments, cwd, environment):
    result = subprocess.run(arguments, cwd=cwd, env=environment, text=True,
                            capture_output=True, timeout=20)
    if result.returncode:
        raise AssertionError((arguments, result.returncode, result.stdout, result.stderr))
    return result.stdout


def target(database, name):
    match = re.search(r'^' + re.escape(name) + r':[^\n]*\n(.*?)(?=\n\n|\Z)',
                      database, re.M | re.S)
    if not match:
        raise AssertionError(f'missing generated target {name}')
    return '\n'.join(line for line in match.group(0).splitlines()
                     if not line.startswith('#'))


def generate(script, configuration, system, custom_source=False):
    with tempfile.TemporaryDirectory(prefix='socket-image-rules-') as temporary:
        root = Path(temporary)
        source = root / ('custom-source' if custom_source else 'Modules')
        source.mkdir()
        (source / 'socketmodule.c').write_text('')
        (source / 'probe.c').write_text('')
        (root / 'Setup').write_text(configuration)
        (root / 'config.c.in').write_text('/* MARKER 1 */\n/* MARKER 2 */\n')
        (root / 'Makefile.pre').write_text('''
MODBUILT_NAMES=_MODBUILT_NAMES_
MODSHARED_NAMES=_MODSHARED_NAMES_
MODDISABLED_NAMES=_MODDISABLED_NAMES_
MODOBJS=_MODOBJS_
MODLIBS=_MODLIBS_
# Definitions added by makesetup
MACHDEP=''' + ('darwin' if system == 'Darwin' else 'linux') + '''
SOCKET_C_IMAGE_ENABLED=$(and $(SOCKET_C_IMAGE_DEFINITIONS),$(filter darwin,$(MACHDEP)),$(filter _socket,$(MODSHARED_NAMES)),$(filter _socket_rs,$(MODSHARED_NAMES)))
EXT_SUFFIX=.so
CARGO_DYLIB_SUFFIX=.dylib
CARGO_TARGET_DIR=release
CC=never-invoke-compiler
BLDSHARED_EXE=never-invoke-linker
BLDSHARED_ARGS=-bundle -undefined dynamic_lookup
MODULE__SOCKET_CFLAGS=-DC_SOCKET_CUSTOM
PY_STDMODULE_CFLAGS=-O2 -DCONFIGURED_NATIVE
CCSHARED=-fPIC
PY_BUILTIN_MODULE_CFLAGS=-O2 -DBUILTIN=1
abs_builddir=/unchanged/build
srcdir=.
.PHONY: configuration-proof
configuration-proof:
\t@echo configuration-only
''')
        bindir = root / 'bin'
        bindir.mkdir()
        uname = bindir / 'uname'
        uname.write_text('#!/bin/sh\nprintf "%s\\n" "' + system + '"\n')
        uname.chmod(0o755)
        environment = dict(os.environ, PATH=str(bindir) + os.pathsep + os.environ['PATH'])
        invoke(['/bin/sh', str(script), '-s', source.name, '-c', 'config.c.in',
                '-m', 'Makefile.pre', 'Setup'], root, environment)
        generated = (root / 'Makefile').read_text()
        config = (root / 'config.c').read_text()
        database = invoke([OPTIONS.make, '-f', 'Makefile', '-np', 'configuration-proof'], root, environment)
        inventory = {name: re.search(r'^' + name + r'=\s*(.*)$', generated, re.M).group(1).split()
                     for name in ('MODBUILT_NAMES', 'MODSHARED_NAMES', 'MODDISABLED_NAMES')}
        result = {'inventory': inventory, 'config': config,
                  'probe': target(database, source.name + '/_probe.so')}
        if '_socket' in inventory['MODSHARED_NAMES']:
            result['c'] = target(database, source.name + '/_socket.so')
            result['compile'] = invoke([OPTIONS.make, '-f', 'Makefile', '-n',
                                        source.name + '/socketmodule.o'], root, environment)
        if '_socket_rs' in inventory['MODSHARED_NAMES']:
            result['helper'] = target(database, source.name + '/_socket_rs.so')
            result['cargo'] = target(database, 'target/release/lib_socket_rs.dylib')
        # Temporary fixture paths are observer identities, not build variables.
        return {key: value.replace(str(root), '<fixture>') if isinstance(value, str) else value
                for key, value in result.items()}


C = '_socket socketmodule.c\n'
RUST = '_socket_rs _socket_rs/Cargo.toml _socket_rs/src/lib.rs\n'
PROBE = '_probe probe.c -DPROBE\n'


class SocketImageRuleContracts(unittest.TestCase):
    def compare(self, configuration, system='Darwin', custom_source=False, active=False):
        original = generate(OPTIONS.original, configuration, system, custom_source)
        candidate = generate(OPTIONS.candidate, configuration, system, custom_source)
        for key in ('inventory', 'config', 'probe'):
            self.assertEqual(candidate[key], original[key], key)
        if active:
            self.assertIn('ln -s _socket_rs$(EXT_SUFFIX)', candidate['c'])
            self.assertNotIn('$(BLDSHARED_EXE)', candidate['c'])
            self.assertIn('/socketmodule.o', candidate['cargo'])
            self.assertEqual(candidate['cargo'].count('cargo build'), 1)
            self.assertIn('SOCKET_C_IMAGE=1', candidate['cargo'])
            self.assertIn('cp target/', candidate['helper'])
            self.assertIn('-DPyInit__socket=_PySocket_CImage_Init', candidate['compile'])
            self.assertIn('-DC_SOCKET_CUSTOM', candidate['compile'])
            self.assertIn('-DCONFIGURED_NATIVE', candidate['compile'])
            self.assertIn('-fPIC', candidate['compile'])
            self.assertNotIn('-DPyInit__socket=', original['compile'])
            self.assertNotIn('ln -s', original['c'])
        else:
            for key in ('c', 'compile', 'helper', 'cargo'):
                if key in original:
                    self.assertEqual(candidate[key], original[key], key)

    def test_shared_members_in_both_orders(self):
        for members in (C + RUST, RUST + C):
            with self.subTest(members=members):
                self.compare('*shared*\n' + members + PROBE, active=True)

    def test_missing_disabled_and_static_partners(self):
        for configuration in (
            '*shared*\n' + C + PROBE,
            '*shared*\n' + RUST + PROBE,
            '*disabled*\n_socket\n*shared*\n' + C + RUST + PROBE,
            '*disabled*\n_socket_rs\n*shared*\n' + RUST + C + PROBE,
            '*static*\n' + C + '*shared*\n' + RUST + PROBE,
            '*static*\n' + RUST + '*shared*\n' + C + PROBE,
        ):
            with self.subTest(configuration=configuration):
                self.compare(configuration)

    def test_non_darwin_and_custom_source_flags(self):
        self.compare('*shared*\n' + C + RUST + PROBE, system='Linux')
        self.compare('*shared*\n' + C + RUST + PROBE, custom_source=True)

    def test_custom_definitions_keep_original_rules(self):
        for members in (C.replace('socketmodule.c', 'socketmodule.c -DCUSTOM_USER') + RUST,
                        C + RUST.replace('_socket_rs/Cargo.toml', '_socket_rs/other.toml'),
                        C + RUST.replace('_socket_rs/src/lib.rs', '_socket_rs/src/other.rs')):
            with self.subTest(members=members):
                self.compare('*shared*\n' + members + PROBE)

    def test_custom_source_keeps_original_rules(self):
        self.compare('*shared*\n' + C + RUST + PROBE, custom_source=True)

    def test_original_standalone_fails_merged_image_contract(self):
        original = generate(OPTIONS.original, '*shared*\n' + C + RUST + PROBE, 'Darwin')
        self.assertNotIn('ln -s _socket_rs$(EXT_SUFFIX)', original['c'])
        self.assertNotIn('SOCKET_C_IMAGE=1', original['cargo'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--original', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--make', required=True)
    OPTIONS, remaining = parser.parse_known_args()
    OPTIONS.original = OPTIONS.original.resolve()
    OPTIONS.candidate = OPTIONS.candidate.resolve()
    assert hashlib.sha256(OPTIONS.original.read_bytes()).hexdigest() == ORIGINAL_SHA256
    unittest.main(argv=[__file__, *remaining])
