"""Build the macOS release CSV, JSON, typing, tokenize, datetime, threading and UUID helpers against one source-built abort std.

The ordinary workspace, helper bodies and Cargo lock are unchanged. Host build
scripts retain their installed host runtime. Target libraries instead receive
code and full metadata from a single freshly compiled standard-library graph.
The completed receipt binds exactly seven named consumer artifacts to that provider;
module publication copies signed bytes only after the entire receipt verifies.

An unrestricted provider supplies consumer code/full metadata first. A second
link uses only those consumers' actual provider-bound imports and explicit
runtime roots; publication requires identical full metadata and a proved export
closure. Original compiler outputs remain immutable. This intentionally narrows
the private Rust provider ABI while preserving the native Python API boundary.
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
import stat
import subprocess
import tarfile
import tomllib

TARGET = 'aarch64-apple-darwin'
CONSUMERS = ('_csv_rs', '_json_rs', '_typing_rs', '_tokenize_rs', '_datetime_rs', '_threading_rs', '_uuid_rs')
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
    return args in (['-vV'], ['--version'], ['--verbose', '--version']) or any(x == '--print' or x.startswith('--print=') for x in args)


def host_capability_probe(args, environment, cwd, source_files, target_directory):
    if '--cfg=procmacro2_build_probe' not in args:
        return False
    package = Path(cwd).resolve()
    if (environment.get('CARGO_PKG_NAME') != 'proc-macro2'
            or environment.get('CARGO_PKG_VERSION') != '1.0.107'
            or environment.get('CARGO_MANIFEST_DIR') != str(package)
            or environment.get('HOST') != TARGET or environment.get('TARGET') != TARGET):
        raise ValueError('host capability probe package/host identity changed')
    sources = [x for x in args if x.endswith('.rs')]
    if len(sources) != 1 or sources[0] not in {
        'src/probe/proc_macro_span.rs', 'src/probe/proc_macro_span_location.rs',
        'src/probe/proc_macro_span_file.rs'}:
        raise ValueError('host capability probe source is not admitted')
    for path in (package / 'build.rs', package / 'Cargo.toml', package / sources[0]):
        if str(path) not in source_files or digest(path) != source_files[str(path)]:
            raise ValueError('host capability probe source is not frozen')
    out = Path(environment['OUT_DIR']).resolve()
    parent = Path(target_directory).resolve() / 'release/build/proc-macro2'
    if not out.is_relative_to(parent) or len(out.relative_to(parent).parts) != 2 or out.name != 'out':
        raise ValueError('host capability probe output owner changed')
    if environment.get('RUSTC') != str(Path(target_directory).resolve().parent / 'rustc-logger.py'):
        raise ValueError('host capability probe compiler wrapper changed')
    expected = ['--cfg=procmacro2_build_probe', '--edition=2021', '--crate-name=proc_macro2',
                '--crate-type=lib', '--cap-lints=allow', '--emit=dep-info,metadata',
                '--out-dir', str(out / 'probe'), sources[0], '--target', TARGET]
    encoded = environment.get('CARGO_ENCODED_RUSTFLAGS', '')
    if encoded:
        expected.extend(encoded.split('\x1f'))
    if list(args) != expected:
        raise ValueError('host capability probe invocation changed')
    return True


def verify_compiler_units(units, source_files, target_directory):
    for unit in units:
        probe = host_capability_probe(unit['original_argv'][1:], unit['environment'],
                                      unit['cwd'], source_files, target_directory)
        if probe:
            # Build-script probes intentionally turn ordinary compiler rejection
            # into feature availability. They must use their unchanged host
            # runtime; injecting target std changes that feature detection.
            if unit['argv'] != unit['original_argv']:
                raise ValueError('host capability probe arguments changed')
            source = next(x for x in unit['original_argv'] if x.endswith('.rs'))
            path = str((Path(unit['cwd']) / source).resolve())
            if unit['source_files'] != {path: source_files[path]}:
                raise ValueError('host capability probe source receipt changed')
            if unit['exit_code'] not in (0, 1) or unit['reaped_exit'] != unit['exit_code']:
                raise ValueError('host capability probe did not complete normally')
        elif unit['exit_code'] != 0 or unit['reaped_exit'] != 0:
            raise ValueError('failed compiler unit in completed receipt')
        verify_files(unit['source_files'])


def target_arguments(original, pairs, directories, target_sysroot=None):
    args = list(original)
    if is_query(args) or '--target' not in args or args[args.index('--target') + 1] != TARGET:
        return args
    # Explicit code/full-metadata pairs select the source runtime. The owned
    # target sysroot also prevents implicit no_std core lookup from escaping
    # to the installed runtime; ordinary host compiler units return unchanged.
    for name in ('std', 'core', 'alloc'):
        if any(x.split('=', 1)[0].split(':')[-1] == name for i, x in enumerate(args)
               if i and args[i - 1] == '--extern'):
            raise ValueError('unexpected existing runtime extern: ' + name)
    for name in ('std', 'core', 'alloc'):
        for path in pairs[name]:
            args.extend(['--extern', name + '=' + path])
    if target_sysroot is None:
        raise ValueError('target compiler requires an owned sysroot')
    positions = [i for i, arg in enumerate(args) if arg == '--sysroot']
    if len(positions) != 1 or positions[0] + 1 >= len(args) or any(arg.startswith('--sysroot=') for arg in args):
        raise ValueError('target compiler requires exactly one explicit sysroot')
    args[positions[0] + 1] = str(target_sysroot)
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


# These unmangled entry points are a runtime boundary even when a particular
# consumer does not emit a reference. Allocation roots below are selected by
# their exact Rust v0 namespace and identifier, never a substring match.
EXPORT_SAFETY_ROOTS = ('_rust_eh_personality',)
DARWIN_WEAK_EXPORTS = ('___isOSVersionAtLeast', '___isPlatformVersionAtLeast')
ALLOCATOR_EXPORT_ROOTS = ('__rust_alloc', '__rust_dealloc', '__rust_realloc',
                          '__rust_alloc_zeroed', '__rust_no_alloc_shim_is_unstable_v2')


def macho_link_surface(data):
    """Read the frozen arm64 dylib link surface; unsupported encodings fail closed."""
    import _struct as struct
    def require(condition, message):
        if not condition:
            raise ValueError('source std Mach-O: ' + message)
    def unpack(fmt, offset, end=None):
        end = len(data) if end is None else end
        require(0 <= offset <= end - struct.calcsize(fmt) <= len(data), 'truncated field')
        return struct.unpack_from(fmt, data, offset)
    def string(blob, offset):
        require(0 <= offset < len(blob), 'string offset')
        end = blob.find(b'\0', offset)
        require(end >= offset, 'unterminated string')
        try:
            value = blob[offset:end].decode('ascii')
        except UnicodeDecodeError as error:
            raise ValueError('source std Mach-O: non-ASCII link symbol') from error
        require(bool(value) and '\n' not in value and '\r' not in value, 'invalid link name')
        return value, end + 1
    def leb(blob, offset, signed=False):
        value, shift = 0, 0
        while True:
            require(offset < len(blob) and shift < 64, 'invalid LEB')
            byte = blob[offset]
            offset += 1
            value |= (byte & 127) << shift
            shift += 7
            if not byte & 128:
                if signed and byte & 64:
                    value -= 1 << shift
                require(-(1 << 63) <= value < (1 << 63) if signed else value < 1 << 64, 'LEB overflow')
                return value, offset
    magic, cpu, _, kind, count, length, flags, reserved = unpack('<8I', 0)
    require(magic == 0xfeedfacf and cpu == 0x100000c and kind == 6
            and reserved == 0 and flags & 0x80, 'expected two-level arm64 dylib')
    end, position = 32 + length, 32
    require(end <= len(data) and count <= length // 8, 'command extent')
    loads, segments, binds, tries, chained = [], [], [], [], []
    identity = None
    for _ in range(count):
        tag, size = unpack('<II', position, end)
        require(size >= 8 and size % 8 == 0 and position + size <= end, 'command alignment/extent')
        if tag == 0x19:
            require(size >= 72, 'segment command')
            vmaddr, vmsize, fileoff, filesize, _, _, sections, _ = unpack('<4Q4I', position + 24, position + size)
            require(size == 72 + sections * 80 and vmaddr + vmsize <= 1 << 64
                    and fileoff + filesize <= len(data), 'segment extent')
            segments.append({'vmaddr': vmaddr, 'vmsize': vmsize, 'fileoff': fileoff, 'filesize': filesize})
        elif tag in (12, 13, 0x20, 0x80000018, 0x8000001f, 0x80000023):
            require(size >= 24, 'dylib command')
            offset, = unpack('<I', position + 8, position + size)
            require(24 <= offset < size, 'dylib name')
            name, _ = string(data[position:position + size], offset)
            if tag == 13:
                require(identity is None, 'duplicate install identity')
                identity = name
            else:
                require(tag == 12, 'weak/reexport/upward/lazy dependency')
                loads.append(name)
        elif tag in (0x22, 0x80000022):
            require(size == 48, 'dyld info extent')
            values = unpack('<10I', position + 8, position + size)
            require(values[5] == 0, 'weak lookup stream unsupported')
            binds.extend((values[index], values[index + 1], lazy)
                         for index, lazy in ((2, False), (6, True)))
            tries.append((values[8], values[9]))
        elif tag in (0x80000033, 0x80000034):
            require(size == 16, 'linkedit command extent')
            pair = unpack('<II', position + 8, position + size)
            (tries if tag == 0x80000033 else chained).append(pair)
        position += size
    require(position == end and identity is not None and len(chained) <= 1, 'incomplete dylib layout')
    def payload(offset, length):
        require(offset >= end and offset + length <= len(data), 'linkedit bounds')
        return data[offset:offset + length]
    imports = []
    for offset, length, lazy in binds:
        if not length:
            continue
        stream = payload(offset, length)
        cursor, ordinal, symbol, weak, segment, address, bind_kind, addend = 0, 0, None, False, None, 0, 1, 0
        def emit():
            require(bind_kind == 1 and symbol is not None and segment is not None
                    and address + 8 <= segments[segment]['vmsize'], 'binding address/type')
            imports.append({'ordinal': ordinal, 'weak': weak, 'symbol': symbol, 'addend': addend})
        while cursor < len(stream):
            byte = stream[cursor]
            cursor += 1
            opcode, immediate = byte & 0xf0, byte & 15
            if opcode == 0:
                if not lazy:
                    require(not any(stream[cursor:]), 'bind trailing data')
                    break
                ordinal, symbol, weak, segment, address, bind_kind, addend = 0, None, False, None, 0, 1, 0
            elif opcode == 0x10:
                ordinal = immediate
            elif opcode == 0x20:
                ordinal, cursor = leb(stream, cursor)
            elif opcode == 0x30:
                ordinal = immediate - 16 if immediate else 0
            elif opcode == 0x40:
                require(immediate in (0, 1), 'symbol flags')
                symbol, cursor = string(stream, cursor)
                weak = bool(immediate)
            elif opcode == 0x50:
                bind_kind = immediate
            elif opcode == 0x60:
                addend, cursor = leb(stream, cursor, True)
            elif opcode == 0x70:
                segment = immediate
                require(segment < len(segments), 'bind segment')
                address, cursor = leb(stream, cursor)
            elif opcode == 0x80:
                advance, cursor = leb(stream, cursor)
                address = (address + advance) & ((1 << 64) - 1)
            elif opcode in (0x90, 0xa0, 0xb0):
                emit()
                advance = 0
                if opcode == 0xa0:
                    advance, cursor = leb(stream, cursor)
                elif opcode == 0xb0:
                    advance = immediate * 8
                address = (address + 8 + advance) & ((1 << 64) - 1)
            elif opcode == 0xc0:
                repetitions, cursor = leb(stream, cursor)
                skip, cursor = leb(stream, cursor)
                require(repetitions <= len(data) // 8, 'bind repetition bounds')
                for _ in range(repetitions):
                    emit()
                    address = (address + 8 + skip) & ((1 << 64) - 1)
            else:
                raise ValueError('source std Mach-O: unsupported bind opcode')
    for offset, length in chained:
        blob = payload(offset, length)
        require(len(blob) >= 28, 'fixups header')
        version, starts, table, strings, count, encoding, symbol_format = struct.unpack_from('<7I', blob)
        require(version == 0 and symbol_format == 0 and encoding in (1, 2, 3), 'fixups encoding')
        width = {1: 4, 2: 8, 3: 16}[encoding]
        require(28 <= starts < len(blob) and 28 <= table <= strings < len(blob)
                and table + width * count <= strings, 'fixups table extent')
        import_table = []
        for index in range(count):
            bits, = struct.unpack_from('<Q' if encoding == 3 else '<I', blob, table + index * width)
            if encoding == 3:
                require((bits >> 17) & 0x7fff == 0, 'fixups reserved bits')
                ordinal, weak, name = bits & 65535, bool((bits >> 16) & 1), bits >> 32
                ordinal = ordinal - 65536 if ordinal >= 32768 else ordinal
            else:
                ordinal, weak, name = bits & 255, bool((bits >> 8) & 1), bits >> 9
                ordinal = ordinal - 256 if ordinal >= 128 else ordinal
            addend = 0
            if encoding == 2:
                addend, = struct.unpack_from('<i', blob, table + index * width + 4)
            elif encoding == 3:
                addend, = struct.unpack_from('<q', blob, table + index * width + 8)
            symbol, _ = string(blob, strings + name)
            import_table.append({'ordinal': ordinal, 'weak': weak, 'symbol': symbol, 'addend': addend})
        # Import-table addends alone do not describe a binding: each supported
        # 64-bit pointer carries an unsigned eight-bit addend as well.
        require(starts + 4 <= len(blob), 'fixups starts header')
        segment_count, = struct.unpack_from('<I', blob, starts)
        require(segment_count == len(segments) and starts + 4 + segment_count * 4 <= table,
                'fixups starts segment roster')
        base = min((segment['vmaddr'] for segment in segments if segment['filesize']), default=0)
        visited_sites = set()
        for segment_index, segment in enumerate(segments):
            relative, = struct.unpack_from('<I', blob, starts + 4 + segment_index * 4)
            if relative == 0:
                continue
            begin = starts + relative
            require(starts + 4 + segment_count * 4 <= begin <= table - 22, 'fixups segment header')
            total, page_size, pointer_format, segment_offset, maximum, pages = struct.unpack_from('<IHHQIH', blob, begin)
            require(total >= 22 + pages * 2 and total % 2 == 0 and begin + total <= table
                    and page_size in (4096, 16384) and pointer_format in (2, 6) and maximum == 0
                    and segment_offset == segment['vmaddr'] - base
                    and pages * page_size <= segment['vmsize'] + page_size - 1,
                    'fixups segment layout/format')
            for page in range(pages):
                page_start, = struct.unpack_from('<H', blob, begin + 22 + page * 2)
                if page_start == 65535:
                    continue
                chain_starts = [page_start]
                if page_start & 0x8000:
                    extra_index = page_start & 0x7fff
                    require(extra_index >= pages, 'fixups multi-start index')
                    chain_starts = []
                    while True:
                        require(22 + 2 * extra_index + 2 <= total, 'fixups multi-start extent')
                        entry, = struct.unpack_from('<H', blob, begin + 22 + 2 * extra_index)
                        chain_starts.append(entry & 0x7fff)
                        extra_index += 1
                        if entry & 0x8000:
                            break
                for within in chain_starts:
                    while True:
                        site = page * page_size + within
                        require(within % 4 == 0 and within + 8 <= page_size
                                and site + 8 <= segment['filesize'] and site + 8 <= segment['vmsize']
                                and (segment_index, site) not in visited_sites,
                                'fixups pointer site bounds/overlap')
                        visited_sites.add((segment_index, site))
                        bits, = unpack('<Q', segment['fileoff'] + site)
                        if bits >> 63:
                            require((bits >> 32) & 0x7ffff == 0, 'fixups pointer reserved bits')
                            index = bits & 0xffffff
                            require(index < len(import_table), 'fixups pointer import index')
                            addend = (bits >> 24) & 255
                            entry = import_table[index]
                            combined = entry['addend'] + addend
                            require(-(1 << 63) <= combined < 1 << 63, 'fixups combined addend overflow')
                            imports.append({**entry, 'addend': combined})
                        advance = (bits >> 51) & 0xfff
                        if advance == 0:
                            break
                        within += advance * 4
    exports = {}
    nonempty_tries = [(offset, length) for offset, length in tries if length]
    require(len(nonempty_tries) <= 1, 'duplicate exports trie')
    for offset, length in nonempty_tries:
        blob = payload(offset, length)
        stack, visited = [(0, '')], set()
        while stack:
            node, name = stack.pop()
            require(node not in visited and node < len(blob), 'trie cycle/shared node')
            visited.add(node)
            terminal, cursor = leb(blob, node)
            terminal_end = cursor + terminal
            require(terminal_end < len(blob), 'trie terminal extent')
            if terminal:
                export_flags, value_cursor = leb(blob, cursor)
                # Regular, thread-local and weak-regular exports share one
                # address ULEB. Preserve the exact kind for replay comparison.
                require(export_flags in (0, 1, 4) and name and name not in exports,
                        'unsupported/duplicate export name=' + repr(name) + ' flags=' + str(export_flags))
                _, value_cursor = leb(blob, value_cursor)
                require(value_cursor == terminal_end, 'export terminal data')
                exports[name] = export_flags
            children = blob[terminal_end]
            cursor = terminal_end + 1
            for _ in range(children):
                edge, cursor = string(blob, cursor)
                child, cursor = leb(blob, cursor)
                require(len(name) + len(edge) <= len(blob), 'trie name bounds')
                stack.append((child, name + edge))
    for row in imports:
        require(row['ordinal'] <= len(loads), 'import ordinal bounds')
    return {'install_id': identity, 'loads': loads, 'imports': imports, 'exports': exports}


def provider_export_closure(provider, consumers, native_api=None):
    if set(consumers) != set(CONSUMERS):
        raise ValueError('export closure consumer roster changed')
    exports = provider['exports']
    safety = set(EXPORT_SAFETY_ROOTS) | set(DARWIN_WEAK_EXPORTS)
    for name in ALLOCATOR_EXPORT_ROOTS:
        matches = [s for s in exports if re.fullmatch(r'__RNvCs[0-9A-Za-z]+_7___rustc'
                   + str(len(name)) + '_' + re.escape(name), s)]
        if len(matches) != 1:
            raise ValueError('missing or ambiguous allocator safety root: ' + name)
        safety.add(matches[0])
    metadata = [s for s in exports if re.fullmatch(r'_rust_metadata_std_[0-9a-f]{16}', s)]
    if len(metadata) != 1:
        raise ValueError('missing or ambiguous metadata safety root')
    safety.add(metadata[0])
    if not safety <= exports.keys():
        raise ValueError('missing provider safety root')
    if {s for s, flags in exports.items() if flags & 4} != set(DARWIN_WEAK_EXPORTS):
        raise ValueError('unexpected provider weak definition')
    # Runtime dlsym names in the pinned Darwin source are platform C names.
    # Keep every unmangled provider entry; newly introduced ones require review.
    if any(not s.startswith('__R') and s not in safety for s in exports):
        raise ValueError('unreviewed unmangled provider export')
    if provider['loads'] != ['/usr/lib/libSystem.B.dylib']:
        raise ValueError('provider dependency identity is not the reviewed System closure')
    for row in provider['imports']:
        ordinal = row['ordinal']
        if ordinal != 1 or row['weak']:
            raise ValueError('unexpected provider import/self/weak lookup')
    symbols, observations = set(safety), {}
    for name, consumer in consumers.items():
        if consumer['loads'].count(provider['install_id']) != 1:
            raise ValueError('consumer lacks exact original provider install identity: ' + name)
        ordinal = consumer['loads'].index(provider['install_id']) + 1
        observations[name] = []
        for row in consumer['imports']:
            if row['weak']:
                raise ValueError('unsupported weak consumer binding')
            if row['ordinal'] == -2:
                symbol = row['symbol']
                if (native_api is None or not symbol.startswith(('_Py', '__Py'))
                        or native_api['exports'].get(symbol) != 0):
                    raise ValueError('flat consumer binding lacks its exact strong native Python definition')
                continue
            if not 1 <= row['ordinal'] <= len(consumer['loads']):
                raise ValueError('unsupported self/flat consumer binding')
            if row['ordinal'] == ordinal:
                if row['symbol'] not in exports:
                    raise ValueError('consumer import lacks provider definition: ' + row['symbol'])
                symbols.add(row['symbol'])
                observations[name].append(row['symbol'])
    return {'symbols': sorted(symbols), 'safety_roots': sorted(safety),
            'consumer_imports': observations, 'provider_surface': provider,
            'consumer_surfaces': consumers, 'native_api_surface': native_api}


def replace_provider_export_argument(arguments, exports_path, expected_output):
    arguments = list(arguments)
    positions = [i for i, arg in enumerate(arguments) if 'exported_symbols_list' in arg]
    if (len(positions) != 1 or arguments[positions[0]] != '-Wl,-exported_symbols_list'
            or any(arg.startswith('@') for arg in arguments)
            or arguments.count('-o') != 1 or '-dynamiclib' not in arguments):
        raise ValueError('unsupported or multiple provider export policies')
    index = positions[0]
    if index + 1 >= len(arguments) or not arguments[index + 1].startswith('-Wl,/'):
        raise ValueError('missing split provider export-list path')
    generated = Path(arguments[index + 1][4:])
    if (',' in str(generated) or generated.name != 'list' or not generated.parent.name.startswith('rustc')
            or arguments[arguments.index('-o') + 1] != str(expected_output)
            or not exports_path.is_absolute() or ',' in str(exports_path)):
        raise ValueError('provider export-list/output ownership changed')
    arguments[index + 1] = '-Wl,' + str(exports_path)
    return arguments, generated


def producer_linker_positions(arguments, pinned_clang=None):
    positions = [i for i, arg in enumerate(arguments) if arg.startswith('linker=')]
    if (not positions or any(i == 0 or arguments[i - 1] != '-C' for i in positions)
            or any(arg.startswith(('-Clinker', '-C=linker', '--codegen=linker')) for arg in arguments)
            or len({arguments[i] for i in positions}) != 1):
        raise ValueError('producer must have one explicit original linker identity')
    if pinned_clang is not None and arguments[positions[0]] != 'linker=' + pinned_clang:
        raise ValueError('producer original linker differs from pinned clang')
    return positions


def restricted_producer_arguments(original, output, linker_path):
    arguments = producer_arguments(original, output)
    positions = producer_linker_positions(arguments)
    # Cargo can repeat the same linker through target settings and codegen flags.
    # Rustc uses the last setting; retain earlier settings and every other argument.
    arguments[positions[-1]] = 'linker=' + str(linker_path)
    return arguments


def provider_linker_main(config_path, config_sha256, arguments):
    # The outer owned rustc group also owns clang: no new session is created.
    if digest(config_path) != config_sha256 or digest(__file__) != os.environ['CSV_SOURCE_STD_LINKER_SHA256']:
        raise ValueError('provider linker source/config identity changed')
    config = json.loads(Path(config_path).read_text())
    verify_files(config['files'])
    exports = Path(config['exports']['path'])
    replaced, generated = replace_provider_export_argument(arguments, exports, Path(config['output']))
    root = Path(config['root'])
    if (generated.resolve(strict=True) != generated or not generated.is_relative_to(root)
            or generated.is_symlink()):
        raise ValueError('generated export list escaped its owned temporary directory')
    before = generated.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise ValueError('generated export list is not a private regular file')
    data = generated.read_bytes()
    after = generated.stat()
    if (any(getattr(before, key) != getattr(after, key) for key in ('st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))
            or sorted(data.decode().splitlines()) != config['full_exports']):
        raise ValueError('original generated export list differs from full provider surface')
    retained = root / 'original-provider-exports.txt'
    with retained.open('xb') as stream:
        stream.write(data)
    compiler_pgid = os.getpgrp()
    parent_pid = os.getppid()
    if compiler_pgid != parent_pid:
        raise ValueError('provider linker does not inherit its owned compiler group')
    row = {'original_argv': [config['clang'], *arguments],
           'replaced_argv': [config['clang'], *replaced], 'generated_path': str(generated),
           'generated_list': artifact(retained), 'config': artifact(config_path),
           'script': artifact(__file__), 'exports_file': artifact(exports),
           'clang': artifact(config['clang']), 'parent_pid': parent_pid, 'compiler_pgid': compiler_pgid}
    process = None
    try:
        with (root / 'logs/provider-linker.stdout').open('x') as stdout, (root / 'logs/provider-linker.stderr').open('x') as stderr:
            process = subprocess.Popen(row['replaced_argv'], stdout=stdout, stderr=stderr,
                                       pass_fds=jobserver_fds(os.environ.get('CARGO_MAKEFLAGS', '')))
            row.update(pid=process.pid, pgid=os.getpgid(process.pid))
            if row['pgid'] != compiler_pgid:
                raise ValueError('clang escaped the compiler process group')
            row['exit_code'] = process.wait()
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
            row['reaped_exit'] = process.wait()
        verify_files(config['files'])
        row['stdout'] = artifact(root / 'logs/provider-linker.stdout')
        row['stderr'] = artifact(root / 'logs/provider-linker.stderr')
        with (root / 'provider-linker-receipt.json').open('x') as stream:
            stream.write(json.dumps(row, indent=2) + '\n')
    raise SystemExit(row['exit_code'])


def verify_provider_linker(policy, root, compiler_command):
    proof = json.loads(Path(policy['linker_receipt']['path']).read_text())
    config = json.loads(Path(policy['linker_config']['path']).read_text())
    for key in ('linker_script', 'linker_config', 'linker_receipt', 'generated_exports'):
        if artifact(policy[key]['path']) != policy[key]:
            raise ValueError('provider linker proof artifact changed: ' + key)
    verify_files(config['files'])
    replaced, generated = replace_provider_export_argument(proof['original_argv'][1:],
                                                            Path(policy['exports_file']['path']),
                                                            Path(policy['restricted_compiler_artifact']['path']))
    if (proof['replaced_argv'] != [config['clang'], *replaced]
            or proof['original_argv'][0] != config['clang'] or proof['generated_path'] != str(generated)
            or not generated.is_relative_to(root) or proof['generated_list'] != policy['generated_exports']
            or proof['config'] != policy['linker_config'] or proof['script'] != policy['linker_script']
            or proof['exports_file'] != policy['exports_file']
            or sorted(Path(policy['generated_exports']['path']).read_text().splitlines()) != sorted(policy['closure']['provider_surface']['exports'])
            or config['full_exports'] != sorted(policy['closure']['provider_surface']['exports'])
            or config['output'] != policy['restricted_compiler_artifact']['path']
            or config['exports'] != policy['exports_file'] or config['root'] != str(root)
            or proof['parent_pid'] != compiler_command['pid']
            or proof['compiler_pgid'] != compiler_command['pgid'] or proof['pgid'] != compiler_command['pgid']
            or type(proof['pid']) is not int or proof['pid'] <= 1
            or proof['exit_code'] != 0 or proof['reaped_exit'] != 0):
        raise ValueError('provider linker exact replacement/lifecycle proof changed')
    for key in ('clang', 'stdout', 'stderr'):
        if artifact(proof[key]['path']) != proof[key]:
            raise ValueError('provider linker captured artifact changed')
    if config['files'].get(config['clang']) != proof['clang']['sha256']:
        raise ValueError('provider linker lacks pinned clang')


def verify_restricted_provider(full, restricted, closure, full_metadata, restricted_metadata):
    if full_metadata != restricted_metadata:
        raise ValueError('restricted producer full metadata identity changed; no consumer replay is admitted')
    if restricted['exports'] != {s: full['exports'][s] for s in closure['symbols']}:
        raise ValueError('restricted producer export surface differs from exact closure')
    if (restricted['loads'] != full['loads']
            or any(row not in full['imports'] for row in restricted['imports'])):
        raise ValueError('restricted producer introduced an import/dependency outside the full closure')
    if Path(restricted['install_id']).name != Path(full['install_id']).name:
        raise ValueError('restricted producer install basename changed')


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
    for directory in (*(source / 'Modules' / name for name in CONSUMERS), source / 'Modules/cpython-sys',
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


def runtime_output_paths(unit):
    args = unit['argv']
    name = args[args.index('--crate-name') + 1]
    extra = next((args[i + 1].split('=', 1)[1] for i, arg in enumerate(args[:-1])
                  if arg == '-C' and args[i + 1].startswith('extra-filename=')), '')
    folder = Path(args[args.index('--out-dir') + 1])
    code = folder / ('lib' + name + extra + '.rlib')
    full = code.with_suffix('.rmeta')
    return code, full


def runtime_artifacts(unit):
    code, full = runtime_output_paths(unit)
    if not code.is_file() or not full.is_file():
        raise ValueError('missing exact runtime code/full metadata pair: ' + str(code))
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
        identity = str(runtime_output_paths(unit)[1].resolve())
        if identity in selected:
            if selected[identity] != unit:
                raise ValueError('ambiguous runtime compiler identity: ' + name)
            continue
        if unit['exit_code'] or unit['reaped_exit']:
            raise ValueError('failed runtime compiler unit')
        selected[identity] = unit
        for i, arg in enumerate(unit['argv'][:-1]):
            if arg != '--extern':
                continue
            _, raw = unit['argv'][i + 1].split('=', 1)
            # Cargo's extern name can alias a workspace shim. The exact full
            # metadata output, not that source-level name, identifies its unit.
            matches = [u for u in candidates
                       if Path(raw).resolve() in tuple(p.resolve() for p in runtime_output_paths(u))]
            if len(matches) != 1:
                raise ValueError('runtime dependency lacks unique compiler receipt: ' + raw)
            pending.append(matches[0])
    names = {u['argv'][u['argv'].index('--crate-name') + 1] for u in selected.values()}
    if names & {'panic_unwind', 'proc_macro'}:
        raise ValueError('unexpected runtime root in abort std dependency closure')
    return list(selected.values())


def target_sysroot_sources(pairs, std_unit, units):
    # The replayed std pair replaces Cargo's original std pair. Every other
    # runtime crate is the exact reachable code/full-metadata pair from Cargo.
    if set(pairs) != {'std', 'core', 'alloc'} or any(len(pair) != 2 for pair in pairs.values()):
        raise ValueError('target sysroot runtime identities are incomplete')
    paths = list(pairs['std'])
    selected_pairs = {}
    for unit in runtime_closure(std_unit, units):
        args = unit['argv']
        name = args[args.index('--crate-name') + 1]
        if name != 'std':
            pair = [str(path) for path in runtime_artifacts(unit)]
            paths.extend(pair)
            if name in ('core', 'alloc'):
                if name in selected_pairs:
                    raise ValueError('ambiguous target sysroot runtime identity')
                selected_pairs[name] = pair
    sources = {}
    for raw in dict.fromkeys(paths):
        path = Path(raw)
        info = path.lstat()
        if path.resolve(strict=True) != path or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('target sysroot source must be a canonical regular file')
        if path.name in sources:
            raise ValueError('ambiguous target sysroot basename: ' + path.name)
        sources[path.name] = artifact(path)
    if selected_pairs != {name: pairs[name] for name in ('core', 'alloc')}:
        raise ValueError('target sysroot core/alloc pair differs from source runtime closure')
    return sources


def create_target_sysroot(root, pairs, std_unit, units):
    sources = target_sysroot_sources(pairs, std_unit, units)
    if root.resolve(strict=True) != root or not root.is_dir():
        raise ValueError('target sysroot build owner changed')
    view = root / 'target-sysroot'
    view.mkdir()
    directory = view / 'lib/rustlib' / TARGET / 'lib'
    directory.mkdir(parents=True)
    files = []
    for name, source in sorted(sources.items()):
        target = directory / name
        shutil.copyfile(source['path'], target)
        copied = artifact(target)
        if copied['sha256'] != source['sha256'] or copied['size'] != source['size'] or artifact(source['path']) != source:
            raise ValueError('target sysroot source changed while copying')
        files.append({'source': source, 'copy': copied})
    return {'path': str(view), 'files': files}


def verify_target_sysroot(root, record, pairs, std_unit, units):
    view = root / 'target-sysroot'
    if record['path'] != str(view) or view.resolve(strict=True) != view or not view.is_dir():
        raise ValueError('target sysroot owner changed')
    sources = target_sysroot_sources(pairs, std_unit, units)
    directory = view / 'lib/rustlib' / TARGET / 'lib'
    expected = [{'source': source, 'copy': {'path': str(directory / name),
                 'sha256': source['sha256'], 'size': source['size']}}
                for name, source in sorted(sources.items())]
    if record['files'] != expected:
        raise ValueError('target sysroot source closure changed')
    entries = [view / 'lib', view / 'lib/rustlib', view / 'lib/rustlib' / TARGET, directory]
    entries.extend(directory / name for name in sources)
    if any(not path.is_dir() or path.is_symlink() for path in entries[:4]):
        raise ValueError('target sysroot directory inventory changed')
    actual = list(view.rglob('*'))
    if set(actual) != set(entries) or any(path.is_symlink() for path in actual):
        raise ValueError('target sysroot inventory changed')
    for entry in expected:
        path = Path(entry['copy']['path'])
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or artifact(path) != entry['copy']:
            raise ValueError('target sysroot copied runtime changed')


def validate_consumer_cache(source, cargo_home):
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
                raise ValueError('ambiguous consumer lock dependency: ' + raw)
            visit(matches[0])
    for name in CONSUMERS:
        visit(next(p for p in packages if p['name'] == name))
    result, source_files = [], {}
    for package in selected.values():
        if 'source' not in package:
            continue
        matches = list((cargo_home / 'registry/cache').glob('*/' + package['name'] + '-' + package['version'] + '.crate'))
        if len(matches) != 1 or digest(matches[0]) != package['checksum']:
            raise ValueError('consumer registry archive missing or changed: ' + package['name'])
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


def runtime_dependencies(loads_text, commands_text, expected_id, provider_id=None):
    identities, dependencies = [], []
    for block in re.split(r'(?m)^\s*Load command \d+\s*$', commands_text):
        command = re.search(r'(?m)^\s*cmd (LC_\w+)\s*$', block)
        if command is None:
            continue
        kind = command[1]
        if kind not in {'LC_ID_DYLIB', 'LC_LOAD_DYLIB', 'LC_LOAD_WEAK_DYLIB',
                        'LC_REEXPORT_DYLIB', 'LC_LOAD_UPWARD_DYLIB', 'LC_LAZY_LOAD_DYLIB'}:
            continue
        name = re.search(r'(?m)^\s*name (.+?) \(offset \d+\)\s*$', block)
        if name is None:
            raise ValueError('runtime dylib command has no name')
        (identities if kind == 'LC_ID_DYLIB' else dependencies).append(name[1])
    # otool -L includes the image's own ID. Prove its command identity and exact
    # compiler-owned value before treating the remaining entries as loads.
    if identities != [expected_id]:
        raise ValueError('runtime install identity changed')
    listed = [line.strip().split(' (')[0] for line in loads_text.splitlines()[1:]]
    if listed != [expected_id, *dependencies]:
        raise ValueError('runtime ID/load command observations disagree')
    if provider_id is not None and dependencies.count(provider_id) != 1:
        raise ValueError('CSV must reference exactly one source std provider')
    if any(not x.startswith(('/usr/lib/', '/System/Library/Frameworks/'))
           for x in dependencies if x != provider_id):
        raise ValueError('unexpected non-system runtime dependency')
    return dependencies


def consumer_install_id(unit, library, root):
    args = unit['argv']
    if '--crate-type' not in args or args[args.index('--crate-type') + 1] != 'cdylib':
        raise ValueError('consumer output lacks a cdylib compiler unit')
    output = runtime_output_paths(unit)[0].with_suffix('.dylib')
    if (not output.resolve(strict=True).is_relative_to(root.resolve())
            or output.name != library.name):
        raise ValueError('consumer install identity lacks its exact owned compiler artifact')
    return str(output)


def normalized_outputs(provider, consumers, environment, commands, root, units):
    if set(consumers) != set(CONSUMERS):
        raise ValueError('expected exactly CSV, JSON, typing, tokenize, datetime, threading and UUID consumer outputs')
    consumer_ids = {name: consumer_install_id(units[name], path, root) for name, path in consumers.items()}
    for name, path in consumers.items():
        if digest(consumer_ids[name]) != digest(path):
            raise ValueError('consumer release artifact differs from its compiler output before normalization: ' + name)
    install_id = '@rpath/' + provider.name
    run(['/usr/bin/install_name_tool', '-id', install_id, provider], root, environment, root / 'logs/provider-id', commands)
    rpath = '@loader_path/../../rust-cpython'
    for label, path in consumers.items():
        loads = run(['/usr/bin/otool', '-L', path], root, environment, root / ('logs/' + label + '-loads-before'), commands)
        matches = [line.strip().split(' (')[0] for line in loads.splitlines()[1:] if provider.name in line]
        if len(matches) != 1:
            raise ValueError('consumer does not link exactly one source std provider: ' + label)
        if matches[0] != install_id:
            run(['/usr/bin/install_name_tool', '-change', matches[0], install_id, path], root, environment, root / ('logs/' + label + '-provider-id'), commands)
        run(['/usr/bin/install_name_tool', '-add_rpath', rpath, path], root, environment, root / ('logs/' + label + '-rpath'), commands)
    outputs = {'provider': provider, **consumers}
    for label, path in outputs.items():
        run(['/usr/bin/codesign', '--force', '--sign', '-', path], root, environment, root / ('logs/' + label + '-sign'), commands)
        run(['/usr/bin/codesign', '--verify', '--strict', path], root, environment, root / ('logs/' + label + '-verify'), commands)
    observed = {}
    for label, path in outputs.items():
        text = run(['/usr/bin/otool', '-L', path], root, environment, root / ('logs/' + label + '-loads-final'), commands)
        commands_text = run(['/usr/bin/otool', '-l', path], root, environment, root / ('logs/' + label + '-commands-final'), commands)
        dependencies = runtime_dependencies(text, commands_text,
                                            install_id if label == 'provider' else consumer_ids[label],
                                            None if label == 'provider' else install_id)
        paths = re.findall(r'cmd LC_RPATH\s+cmdsize \d+\s+path (.*?) \(offset', commands_text)
        if paths != ([] if label == 'provider' else [rpath]):
            raise ValueError('unexpected runtime search path')
        observed[label] = dependencies
    return install_id, rpath, observed


def consumer_arguments(cargo, source, jobs):
    args = [cargo, 'build', '-vv', '--manifest-path', source / 'Cargo.toml']
    for name in CONSUMERS:
        args.extend(['--package', name])
    return args + ['--target', TARGET, '--release', '--locked', '--offline', '-j' + str(jobs),
                   '-Zhost-config', '-Ztarget-applies-to-host', '--config', 'target-applies-to-host=false']


def consumer_units(units, pairs, target_sysroot=None):
    if set(pairs) != {'std', 'core', 'alloc'}:
        raise ValueError('consumer runtime identities are incomplete')
    selected = {}
    for name in CONSUMERS:
        matches = [u for u in units if not u['query'] and '--crate-name' in u['argv']
                   and u['argv'][u['argv'].index('--crate-name') + 1] == name
                   and '--target' in u['argv'] and u['argv'][u['argv'].index('--target') + 1] == TARGET]
        if len(matches) != 1 or matches[0]['exit_code'] != 0 or matches[0]['reaped_exit'] != 0:
            raise ValueError('consumer lacks one successful target compiler unit: ' + name)
        unit = matches[0]
        if target_sysroot is not None:
            roots = [unit['argv'][i + 1] for i, x in enumerate(unit['argv'][:-1]) if x == '--sysroot']
            if roots != [str(target_sysroot)] or any(x.startswith('--sysroot=') for x in unit['argv']):
                raise ValueError('consumer target sysroot owner changed: ' + name)
        externs = [unit['argv'][i + 1] for i, x in enumerate(unit['argv'][:-1]) if x == '--extern']
        for runtime, pair in pairs.items():
            if len(pair) != 2 or any(runtime + '=' + raw not in externs for raw in pair):
                raise ValueError('consumer compiler runtime pair missing: ' + name + '/' + runtime)
        selected[name] = unit
    return selected


def publish_consumer(source, build, target, name, output, source_metadata):
    build = build.resolve()
    if (target != TARGET or name not in CONSUMERS or output.parent != build / 'Modules'
            or output.resolve() != output or not output.name.startswith(name + '.')
            or not output.name.endswith('.so')):
        raise ValueError('consumer module output has an unexpected owner')
    receipt = verify_build_receipt(source, build, target, source_metadata)
    record = receipt['consumers'][name]
    shutil.copyfile(record['path'], output)
    if artifact(output)['sha256'] != record['sha256']:
        raise ValueError('consumer changed during module publication: ' + name)
    return artifact(output)


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
    if receipt['schema_version'] != 8 or receipt['status'] != 'complete' or receipt['target'] != target:
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
    if set(receipt['consumers']) != set(CONSUMERS):
        raise ValueError('expected exactly CSV, JSON, typing, tokenize, datetime, threading and UUID consumer receipts')
    for label, record in {'provider': receipt['provider'], **receipt['consumers']}.items():
        path = Path(record['path'])
        if not path.resolve().is_relative_to(build) or artifact(path) != {k: record[k] for k in ('path', 'sha256', 'size')}:
            raise ValueError('CSV final artifact changed: ' + label)
    verify_export_policy(receipt, root)
    provider = Path(receipt['provider']['path'])
    if provider.parent != root / 'provider' or receipt['provider']['install_id'] != '@rpath/' + provider.name:
        raise ValueError('provider output placement or identity changed')
    for name, record in receipt['consumers'].items():
        if Path(record['path']) != build / 'target' / target / ('release/lib' + name + '.dylib'):
            raise ValueError('published consumer output placement changed: ' + name)
        if (record['rpath'] != '@loader_path/../../rust-cpython'
                or record['provider_install_id'] != receipt['provider']['install_id']):
            raise ValueError('consumer runtime loader contract changed: ' + name)
    mirror = Path(receipt['provider']['build_mirror_path'])
    if (mirror != build.parent / 'rust-cpython' / Path(receipt['provider']['path']).name
            or mirror.resolve(strict=True) != mirror
            or digest(mirror) != receipt['provider']['sha256']
            or receipt['provider']['build_mirror_sha256'] != receipt['provider']['sha256']):
        raise ValueError('build provider mirror changed')
    owner = mirror.parent / '.csv-source-std-owner.json'
    if json.loads(owner.read_text()) != {'build': str(build)}:
        raise ValueError('build provider mirror owner changed')
    verify_compiler_units(receipt['units'], identity['input_files'], root / 'consumer-target')
    verify_target_sysroot(root, receipt['target_sysroot'], receipt['runtime_pairs'],
                          select_std_unit(receipt['units']), receipt['units'])
    selected = consumer_units(receipt['units'], receipt['runtime_pairs'], root / 'target-sysroot')
    for name, record in receipt['consumers'].items():
        if record['unit_receipt'] != selected[name]:
            raise ValueError('consumer output lacks its successful compiler unit: ' + name)
        if record['install_id'] != consumer_install_id(selected[name], Path(record['artifact_path']), root):
            raise ValueError('consumer compiler-owned install identity changed: ' + name)
        compiled = record['compiler_artifact']
        if (compiled['path'] != record['install_id'] or artifact(compiled['path']) != compiled
                or compiled['sha256'] != record['raw_artifact']['sha256']
                or compiled['size'] != record['raw_artifact']['size']):
            raise ValueError('consumer raw compiler artifact correspondence changed: ' + name)
        final = artifact(record['artifact_path'])
        if final['sha256'] != record['sha256'] or final['sha256'] != record['artifact_sha256']:
            raise ValueError('published consumer differs from final release artifact: ' + name)
        if artifact(source / 'Modules' / name / 'src/lib.rs') != record['source']:
            raise ValueError('consumer source owner changed: ' + name)
    if len(receipt['generated_bindings']) != 1:
        raise ValueError('expected one fresh target C API generation')
    for record in receipt['generated_bindings']:
        if artifact(record['path']) != record:
            raise ValueError('generated C API source changed')
    return receipt


def verify_export_policy(receipt, root):
    if 'export_policy' not in receipt:
        raise ValueError('missing provider export policy')
    policy = receipt['export_policy']
    if policy['schema_version'] != 2:
        raise ValueError('unsupported provider export policy')
    for key in ('full_provider', 'full_metadata', 'restricted_metadata',
                'exports_file', 'restricted_compiler_artifact', 'native_api'):
        if artifact(policy[key]['path']) != policy[key]:
            raise ValueError('provider export policy artifact changed: ' + key)
    full = Path(policy['full_provider']['path'])
    final = Path(receipt['provider']['path'])
    if (full.parent != root / 'full-provider' or full.name != final.name
            or receipt['runtime_pairs']['std'] != [str(full), policy['full_metadata']['path']]
            or Path(policy['restricted_metadata']['path']) != root / 'restricted-provider' / final.with_suffix('.rmeta').name
            or Path(policy['exports_file']['path']) != root / 'provider-exports.txt'
            or Path(policy['restricted_compiler_artifact']['path']) != root / 'restricted-provider' / final.name):
        raise ValueError('provider export policy output owner changed')
    full_surface = macho_link_surface(full.read_bytes())
    consumers = {name: macho_link_surface(Path(record['compiler_artifact']['path']).read_bytes())
                 for name, record in receipt['consumers'].items()}
    native_path = Path(policy['native_api']['path'])
    if native_path != Path(receipt['build']) / 'libpython3.16.dylib':
        raise ValueError('native Python export owner changed')
    closure = provider_export_closure(full_surface, consumers, macho_link_surface(native_path.read_bytes()))
    if closure != policy['closure'] or Path(policy['exports_file']['path']).read_text() != ''.join(s + '\n' for s in closure['symbols']):
        raise ValueError('provider export policy closure changed')
    restricted = macho_link_surface(Path(policy['restricted_compiler_artifact']['path']).read_bytes())
    if restricted != policy['restricted_surface']:
        raise ValueError('restricted compiler surface changed')
    verify_restricted_provider(full_surface, restricted, closure,
                               policy['full_metadata']['sha256'], policy['restricted_metadata']['sha256'])
    published = macho_link_surface(final.read_bytes())
    if (published['exports'] != restricted['exports'] or published['imports'] != restricted['imports']
            or published['loads'] != restricted['loads']
            or published['install_id'] != '@rpath/' + final.name):
        raise ValueError('normalized provider changed its restricted link surface')
    std_unit = select_std_unit(receipt['units'])
    expected_full = producer_arguments(std_unit['argv'], full.parent)
    config = json.loads(Path(policy['linker_config']['path']).read_text())
    launch_clang = receipt['recipe_environment']['PY_CC']
    producer_linker_positions(std_unit['argv'], launch_clang)
    # Cargo records the bound launch spelling; the adapter pins its canonical target.
    if (not Path(launch_clang).is_absolute()
            or config['clang'] != str(Path(launch_clang).resolve(strict=True))):
        raise ValueError('producer canonical clang identity changed')
    expected_restricted = restricted_producer_arguments(std_unit['argv'], root / 'restricted-provider', root / 'provider-linker.py')
    if policy['full_argv'] != expected_full or policy['restricted_argv'] != expected_restricted:
        raise ValueError('provider replay arguments changed')
    for argv in (expected_full, expected_restricted):
        matches = [command for command in receipt['commands'] if command['argv'] == argv]
        if (len(matches) != 1 or matches[0]['exit_code'] != 0 or matches[0]['reaped_exit'] != 0
                or type(matches[0].get('pid')) is not int or matches[0]['pid'] <= 1
                or matches[0].get('pgid') != matches[0]['pid']):
            raise ValueError('provider replay lacks exact successful owned compiler command')
    verify_provider_linker(policy, root, next(command for command in receipt['commands'] if command['argv'] == expected_restricted))
    raw = receipt['provider']['raw_artifact']
    compiled = policy['restricted_compiler_artifact']
    if (raw['path'] != str(final) or raw['sha256'] != compiled['sha256'] or raw['size'] != compiled['size']):
        raise ValueError('restricted compiler/raw final correspondence changed')


class CompilerCleanupError(RuntimeError):
    def __init__(self, report):
        self.report = report
        super().__init__('compiler cleanup faults: ' + json.dumps(report['faults']))


def cleanup_compilers(root):
    # Wrapper children have independent process groups so a failed Cargo process
    # cannot leave native compiler descendants running after this recipe exits.
    report = {'groups': [], 'faults': []}
    for directory in ('std-units', 'consumer-units'):
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


def check_fresh_consumer_outputs(build, target):
    # A fresh joint owner cannot inherit a helper compiled by another Cargo rule.
    for name in CONSUMERS:
        modules = list((build / 'Modules').glob(name + '.*.so'))
        published = build / 'target' / target / ('release/lib' + name + '.dylib')
        if modules or published.exists() or published.is_symlink():
            raise ValueError('pre-existing consumer output requires a clean build: ' + name)


def build_recipe(source, build, target, profile, jobs):
    if sys.platform != 'darwin' or target != TARGET or profile != 'release':
        raise ValueError('source std CSV/JSON/typing/tokenize/datetime/threading/UUID recipe supports macOS arm64 release only')
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
    check_fresh_consumer_outputs(build, target)
    root.mkdir()
    commands, units = [], []
    status = {'schema_version': 8, 'status': 'building', 'commands': commands}
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
        provider_dir = root / 'full-provider'
        provider_dir.mkdir()
        replay = producer_arguments(original, provider_dir)
        run(replay, Path(std_unit['cwd']), source_env, root / 'logs/std-provider', commands)
        extra = next(original[i + 1].split('=', 1)[1] for i, x in enumerate(original[:-1])
                     if x == '-C' and original[i + 1].startswith('extra-filename='))
        provider = provider_dir / ('libstd' + extra + '.dylib')
        metadata = provider.with_suffix('.rmeta')
        pairs = {'std': [str(provider), str(metadata)]}
        directories = []
        runtime_files = {str(metadata): digest(metadata), str(provider): digest(provider)}
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
        target_view = create_target_sysroot(root, pairs, std_unit, units)
        config.update(target_directory=str(root / 'consumer-target'), receipts=str(root / 'consumer-units'),
                      runtime_pairs=pairs, runtime_directories=list(dict.fromkeys(directories)),
                      target_sysroot=target_view['path'])
        config_path.write_text(json.dumps(config, indent=2) + '\n')
        consumer_env = dict(env, CARGO_TARGET_DIR=config['target_directory'], CARGO_NET_OFFLINE='true',
                            RUSTC=str(logger), CSV_SOURCE_STD_RUSTC_CONFIG=str(config_path))
        consumer_args = consumer_arguments(cargo, source, jobs) + [
            '--config', 'host.linker=' + json.dumps(clang),
            '--config', 'target.' + target + '.linker=' + json.dumps(clang),
            '--config', 'target.' + target + '.rustflags=' + json.dumps(flags)]
        run(consumer_args, source, consumer_env, root / 'logs/consumer-build', commands, 900)
        # The normal build's member proof reads Cargo's real verbose transcript.
        # Reused outputs do not emit compiler evidence from a previous invocation.
        sys.stdout.write((root / 'logs/consumer-build.stdout').read_text())
        sys.stderr.write((root / 'logs/consumer-build.stderr').read_text())
        sys.stdout.flush()
        sys.stderr.flush()
        target_units = [json.loads(p.read_text()) for p in (root / 'consumer-units').glob('*.json')]
        verify_compiler_units(target_units, files, root / 'consumer-target')
        verify_target_sysroot(root, target_view, pairs, std_unit, units)
        selected = consumer_units(target_units, pairs, root / 'target-sysroot')
        consumers = {name: root / 'consumer-target' / target / ('release/lib' + name + '.dylib') for name in CONSUMERS}
        # Consumers compile once against the unrestricted code/full-metadata
        # pair. Keep that compiler output immutable even after final publication.
        full_provider = artifact(provider)
        full_surface = macho_link_surface(provider.read_bytes())
        consumer_surfaces = {name: macho_link_surface(path.read_bytes()) for name, path in consumers.items()}
        native_api = artifact(build / 'libpython3.16.dylib')
        native_surface = macho_link_surface(Path(native_api['path']).read_bytes())
        closure = provider_export_closure(full_surface, consumer_surfaces, native_surface)
        exports_path = root / 'provider-exports.txt'
        exports_path.write_text(''.join(symbol + '\n' for symbol in closure['symbols']))
        files[str(exports_path)] = digest(exports_path)
        restricted_directory = root / 'restricted-provider'
        restricted_directory.mkdir()
        producer_linker_positions(original, clang)
        linker_path = root / 'provider-linker.py'
        linker_config = root / 'provider-linker-config.json'
        link_files = {**files, **runtime_files}
        link_files[str(provider)] = digest(provider)
        config_data = {'root': str(root), 'clang': str(Path(clang).resolve(strict=True)),
                       'files': link_files, 'exports': artifact(exports_path),
                       'output': str(restricted_directory / provider.name),
                       'full_exports': sorted(full_surface['exports'])}
        linker_config.write_text(json.dumps(config_data, indent=2) + '\n')
        script_source = Path(__file__).read_text()
        ending = "if __name__ == '__main__':\n    main()"
        if not script_source.endswith(ending + '\n'):
            raise ValueError('provider linker source entrypoint changed')
        linker_path.write_text('#!' + sys.executable + ' -E\n' + script_source[:-len(ending + '\n')]
                               + "if __name__ == '__main__':\n    provider_linker_main("
                               + repr(str(linker_config)) + ', ' + repr(digest(linker_config)) + ', sys.argv[1:])\n')
        linker_path.chmod(0o755)
        for path in (linker_config, linker_path):
            files[str(path)] = digest(path)
        restricted_environment = {**source_env, 'CSV_SOURCE_STD_LINKER_SHA256': digest(linker_path)}
        restricted_argv = restricted_producer_arguments(original, restricted_directory, linker_path)
        run(restricted_argv, Path(std_unit['cwd']), restricted_environment, root / 'logs/std-provider-restricted', commands)
        restricted_compiler = restricted_directory / provider.name
        restricted_metadata = restricted_compiler.with_suffix('.rmeta')
        runtime_files[str(restricted_metadata)] = digest(restricted_metadata)
        restricted_surface = macho_link_surface(restricted_compiler.read_bytes())
        verify_restricted_provider(full_surface, restricted_surface, closure,
                                   digest(metadata), digest(restricted_metadata))
        export_policy = {'schema_version': 2, 'closure': closure, 'full_provider': full_provider,
                         'full_metadata': artifact(metadata), 'restricted_metadata': artifact(restricted_metadata),
                         'full_argv': replay, 'restricted_argv': restricted_argv,
                         'exports_file': artifact(exports_path), 'restricted_surface': restricted_surface,
                         'native_api': native_api, 'linker_script': artifact(linker_path),
                         'linker_config': artifact(linker_config),
                         'linker_receipt': artifact(root / 'provider-linker-receipt.json'),
                         'generated_exports': artifact(root / 'original-provider-exports.txt')}
        # Normalization edits only the final copy. Both replay output directories
        # retain their original compiler bytes and metadata indefinitely.
        export_policy['restricted_compiler_artifact'] = artifact(restricted_compiler)
        (root / 'provider').mkdir()
        provider = root / 'provider' / restricted_compiler.name
        shutil.copyfile(restricted_compiler, provider)
        raw_provider = artifact(provider)
        raw_consumers = {name: artifact(path) for name, path in consumers.items()}
        consumer_ids = {name: consumer_install_id(selected[name], path, root) for name, path in consumers.items()}
        compiler_artifacts = {name: artifact(path) for name, path in consumer_ids.items()}
        install_id, rpath, dependencies = normalized_outputs(provider, consumers, env, commands, root, selected)
        mirror = publish_build_mirror(provider, build)
        records = {}
        for name, path in consumers.items():
            publish = build / 'target' / target / ('release/lib' + name + '.dylib')
            publish.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, publish)
            records[name] = {**artifact(publish), 'artifact_path': str(path), 'artifact_sha256': digest(path),
                             'install_id': consumer_ids[name], 'compiler_artifact': compiler_artifacts[name],
                             'provider_install_id': install_id, 'rpath': rpath, 'dependencies': dependencies[name],
                             'raw_artifact': raw_consumers[name],
                             'source': artifact(source / 'Modules' / name / 'src/lib.rs'), 'unit_receipt': selected[name]}
        verify_files(files)
        verify_files(runtime_files)
        bindings = [unit['generated_c_api_before_compile'] for unit in target_units if 'generated_c_api_before_compile' in unit]
        if len(bindings) != 1:
            raise ValueError('expected one fresh target C API generation')
        receipt = {'schema_version': 8, 'status': 'complete', 'build': str(build), 'target': target,
                   'recipe_environment': recipe_environment(build, inherited),
                   'profile': profile, 'panic': 'abort', 'allocator': 'System', 'compiler': compiler,
                   'source': {'path': str(source), 'workspace_lock_sha256': digest(source / 'Cargo.lock'),
                              'std_source_path': str(library), 'std_archive_sha256': STD_ARCHIVE_SHA256,
                              'std_revision': REVISION, 'std_lock_sha256': STD_LOCK_SHA256, 'input_files': files,
                              'input_receipt': artifact(input_receipt)},
                   'registry_archives': registry, 'std_registry_packages': std_registry, 'runtime_pairs': pairs, 'runtime_files': runtime_files,
                   'target_sysroot': target_view,
                   'provider': {**artifact(provider), 'install_id': install_id, 'dependencies': dependencies['provider'],
                                'raw_artifact': raw_provider, 'build_mirror_path': mirror['path'],
                                'build_mirror_sha256': mirror['sha256']},
                   'consumers': records, 'export_policy': export_policy,
                   'generated_bindings': bindings, 'units': units + target_units, 'commands': commands}
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
    parser.add_argument('operation', choices=['build', 'publish'])
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--target', required=True)
    parser.add_argument('--profile', choices=['release'], required=True)
    parser.add_argument('--jobs', type=int)
    parser.add_argument('--consumer', choices=CONSUMERS)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.operation == 'build':
        if args.jobs is None or args.jobs < 1 or args.consumer is not None or args.output is not None:
            parser.error('build requires positive jobs and no publication arguments')
        build_recipe(args.source, args.build, args.target, args.profile, args.jobs)
    else:
        if args.consumer is None or args.output is None or args.jobs is not None or args.target != TARGET:
            parser.error('publication requires one consumer/output and the supported target')
        metadata = {'sha256': STD_ARCHIVE_SHA256, 'compiler_revision': REVISION,
                    'library_cargo_lock_sha256': STD_LOCK_SHA256}
        publish_consumer(args.source, args.build, args.target, args.consumer, args.output, metadata)



if __name__ == '__main__':
    main()
