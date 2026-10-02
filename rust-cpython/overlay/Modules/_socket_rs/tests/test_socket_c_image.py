import argparse
import ast
import ctypes
import gc
import hashlib
import importlib
import json
import os
from pathlib import Path
import select
import signal
import sys
import threading
import time
import types

NAMES = ('_socket', '_socket_rs')
PINNED_ABI_HEADERS = {'Include/object.h': '0b4b6a8c830520955a30585c2bd469bf1eaa4f1c70f1884adbe8007c2ffcd479', 'Include/moduleobject.h': '17a30772f5ce916798fa77822d45b5ff2615db6b1d8d54bd324442632d7320e1', 'Include/modsupport.h': '043c43b5cba6694767205d93bcf0e0a3e6e4cabf8a5d4f960d44fe6560182813', 'Include/cpython/modsupport.h': 'cc5e06098a9a4f5f15338b65d98999678ebb28454314d2be306ce7f447217c48', 'Include/slots_generated.h': '91aecfb2b478c6aa35a57de83745ecd1c05a7fcd6c902ba73951c37386e81fa9', 'Modules/socketmodule.h': '75727c43a01dedefd96ecf6010b1be4ea1693a969bfceffec9e3183f81188436'}


def definitions(modules):
    # The observer is compiled against the pinned module and ABI headers.
    import _socket_image_fixture as observer
    return {'pinned_abi_headers': PINNED_ABI_HEADERS,
            'modules': {name: observer.module_contract(module)
                        for name, module in modules.items()}}


def api(module):
    import _socket_image_fixture as observer
    capsule = module.CAPI
    table = observer.socket_contract(module)
    assert table['type'] is module.socket
    assert table['error'] is OSError
    assert table['timeout'] is TimeoutError
    return capsule, table


def error_of(function, *args, **kwargs):
    try:
        function(*args, **kwargs)
    except Exception as exc:
        return [type(exc).__module__, type(exc).__name__, str(exc)]
    raise AssertionError('invalid input accepted')


def roundtrip(module, payload=b'original socket image'):
    left, right = module.socketpair()
    try:
        assert left.send(payload) == len(payload)
        assert right.recv(len(payload)) == payload
    finally:
        left.close()
        right.close()
    return hashlib.sha256(payload).hexdigest()


def direct_c():
    assert not any(name in sys.modules for name in NAMES)
    module = importlib.import_module('_socket')
    assert '_socket_rs' not in sys.modules
    digest = roundtrip(module)
    assert '_socket_rs' not in sys.modules
    capsule, table = api(module)
    return {'helper_absent': True, 'digest': digest,
            'definitions': definitions({'_socket': module}),
            'socket_type_inventory': sorted(vars(module.socket)),
            # Version-tag validity changes with type cache use, not type capability.
            'socket_type_flags': module.socket.__flags__ & ~(1 << 19),
            'capsule_type_matches': table['type'] is module.socket}


def direct_helper():
    assert not any(name in sys.modules for name in NAMES)
    helper = importlib.import_module('_socket_rs')
    assert '_socket' not in sys.modules
    assert helper.parse_address(4, '127.0.0.1') == b'\x7f\0\0\1'
    assert helper.format_address(6, b'\0' * 15 + b'\1') == '::1'
    errors = [error_of(helper.parse_address, 4, 'invalid'),
              error_of(helper.send, -1, b'x'), error_of(helper.recv, -1, 1)]
    assert '_socket' not in sys.modules
    return {'c_absent': True, 'errors': errors,
            'definitions': definitions({'_socket_rs': helper})}


def import_order(order):
    assert not any(name in sys.modules for name in NAMES)
    first = importlib.import_module(order[0])
    assert order[1] not in sys.modules
    second = importlib.import_module(order[1])
    assert first is importlib.reload(first)
    assert second is importlib.reload(second)
    import socket
    assert socket._socket_rs is sys.modules['_socket_rs']
    return {'after_first_other_absent': True, 'digest': roundtrip(socket),
            'definitions': definitions({name: sys.modules[name] for name in NAMES})}


def direct_ssl():
    assert not any(name in sys.modules for name in (*NAMES, 'socket', 'ssl', '_ssl'))
    module = importlib.import_module('_ssl')
    native = sys.modules['_socket']
    assert '_socket_rs' not in sys.modules and 'socket' not in sys.modules
    capsule, table = api(native)
    context = module._SSLContext(module.PROTOCOL_TLS_SERVER)
    left, right = native.socketpair()
    try:
        wrapped = context._wrap_socket(left, True, owner=left)
        assert wrapped is not None
    finally:
        left.close()
        right.close()
    return {'helper_absent': '_socket_rs' not in sys.modules,
            'type_owned': table['type'] is native.socket}


def unavailable_and_partial():
    assert '_socket_rs' not in sys.modules and 'socket' not in sys.modules
    class DenyHelper:
        def find_spec(self, fullname, path=None, target=None):
            if fullname == '_socket_rs':
                raise ImportError('controlled socket helper unavailable')
    finder = DenyHelper()
    sys.meta_path.insert(0, finder)
    try:
        facade = importlib.import_module('socket')
        assert facade._socket_rs is None
        assert '_socket_rs' not in sys.modules
        fallback = roundtrip(facade)
        assert facade.inet_pton(facade.AF_INET, '127.0.0.1') == b'\x7f\0\0\1'
    finally:
        sys.meta_path.remove(finder)
    helper = importlib.import_module('_socket_rs')
    importlib.reload(facade)
    assert facade._socket_rs is helper
    original = helper.send
    calls = []
    def counted(*args):
        calls.append(True)
        return original(*args)
    helper.send = counted
    try:
        assert roundtrip(facade) == fallback and calls
    finally:
        helper.send = original
    sys.modules['_socket_rs'] = types.ModuleType('_socket_rs')
    left, right = facade.socketpair()
    try:
        partial = error_of(left.send, b'x')
        assert partial[1] == 'AttributeError'
    finally:
        left.close()
        right.close()
        sys.modules['_socket_rs'] = helper
    return {'fallback_digest': fallback, 'restored_native_calls': len(calls),
            'partial_error': partial}


def buffers_retry_and_timeout():
    import socket
    import _socket_rs as helper
    left, right = socket.socketpair()
    original_send, original_recv = helper.send, helper.recv
    retry = {'send': 0, 'recv': 0}
    try:
        payload = bytearray(b'writeable socket buffer')
        assert left.send(payload) == len(payload)
        assert right.recv(len(payload)) == payload
        payload.extend(b'!')
        view = memoryview(b'readonly socket buffer')
        assert left.send(view) == len(view)
        assert right.recv(len(view)) == view
        view.release()
        noncontiguous = memoryview(b'abcdef')[::2]
        try:
            bad_buffer = error_of(left.send, noncontiguous)
        finally:
            noncontiguous.release()
        def interrupted_send(*args):
            retry['send'] += 1
            return -2 if retry['send'] == 1 else original_send(*args)
        def interrupted_recv(*args):
            retry['recv'] += 1
            return None if retry['recv'] == 1 else original_recv(*args)
        helper.send, helper.recv = interrupted_send, interrupted_recv
        assert left.send(b'retry') == 5 and right.recv(5) == b'retry'
        assert retry == {'send': 2, 'recv': 2}
        helper.send, helper.recv = original_send, original_recv
        def forbidden(*args):
            raise AssertionError('timeout path must use original C fallback')
        helper.recv = forbidden
        right.settimeout(0)
        nonblocking = error_of(right.recv, 1)
        assert nonblocking[1] == 'BlockingIOError'
        right.settimeout(0.01)
        timed = error_of(right.recv, 1)
        assert timed[1] == 'TimeoutError'
        right.settimeout(None)
        helper.recv = original_recv
        class SocketSubtype(socket.socket):
            pass
        subtype = SocketSubtype(fileno=left.detach())
        try:
            assert subtype.send(b'subtype') == 7 and right.recv(7) == b'subtype'
        finally:
            subtype.close()
        closed = error_of(left.send, b'closed')
        assert closed[1] == 'OSError'
        return {'buffer_error': bad_buffer, 'retry': retry,
                'nonblocking': nonblocking, 'timeout': timed, 'closed': closed}
    finally:
        helper.send, helper.recv = original_send, original_recv
        left.close()
        right.close()


def held_capsule_generations():
    import _socket as old
    import _ssl
    import _socket_rs as helper
    held_capsule, old_table = api(old)
    held_type, held_method = old.socket, helper.parse_address
    held_helper = held_method.__self__
    left, right = old.socketpair()
    context = _ssl._SSLContext(_ssl.PROTOCOL_TLS_SERVER)
    sys.modules.pop('_socket')
    sys.modules.pop('_socket_rs')
    del old, helper
    gc.collect()
    fresh = importlib.import_module('_socket')
    fresh_helper = importlib.import_module('_socket_rs')
    fresh_capsule, fresh_table = api(fresh)
    assert old_table['type'] is held_type
    assert fresh_table['type'] is fresh.socket
    assert fresh.socket is not held_type and fresh_capsule is not held_capsule
    assert held_method(4, '127.0.0.1') == fresh_helper.parse_address(4, '127.0.0.1')
    assert held_method.__self__ is held_helper
    try:
        assert left.send(b'old') == 3 and right.recv(3) == b'old'
        wrapped = context._wrap_socket(left, True, owner=left)
        assert wrapped is not None
        newer, peer = fresh.socketpair()
        try:
            wrong_generation = error_of(context._wrap_socket, newer, True)
            assert wrong_generation[1] == 'TypeError'
        finally:
            newer.close()
            peer.close()
    finally:
        left.close()
        right.close()
    return {'distinct_c_generations': True, 'held_helper_binding': True,
            'ssl_old_type_owned': True, 'new_type_rejection': wrong_generation}


def fixed_kernel(mode, source, source_sha256):
    raw = Path(source).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == source_sha256
    tree = ast.parse(raw)
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name in ('_blob', 'k_socket')]
    assert {node.name for node in functions} == {'_blob', 'k_socket'}
    namespace = {}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), 'exec'), namespace)
    import _socket_rs as helper
    saved = {name: getattr(helper, name) for name in ('parse_address', 'format_address', 'send', 'recv')}
    counts = dict.fromkeys(saved, 0)
    if mode == 'counted':
        for name, function in saved.items():
            def counted(*args, _name=name, _function=function):
                counts[_name] += 1
                return _function(*args)
            setattr(helper, name, counted)
    try:
        _, setup = namespace['k_socket']()
        result = setup()()
        if mode == 'counted':
            assert counts == {'parse_address': 3000, 'format_address': 1000, 'send': 200, 'recv': 200}
        else:
            assert not any(counts.values())
        return {'output': result, 'output_sha256': hashlib.sha256(repr(result).encode()).hexdigest(),
                'counts': counts}
    finally:
        for name, function in saved.items():
            setattr(helper, name, function)
        gc.collect()


def concurrent_calls():
    import socket
    import _socket_rs as helper
    failures = []
    barrier = threading.Barrier(4, timeout=5)
    def worker(index):
        try:
            barrier.wait()
            for _ in range(30):
                assert socket.inet_ntop(socket.AF_INET6, helper.parse_address(6, '::1')) == '::1'
                roundtrip(socket, f'concurrent{index}'.encode())
        except BaseException as exc:
            failures.append(repr(exc))
    threads = [threading.Thread(target=worker, args=(index,), daemon=True) for index in range(3)]
    for thread in threads:
        thread.start()
    barrier.wait()
    deadline = time.monotonic() + 10
    for thread in threads:
        thread.join(max(0, deadline - time.monotonic()))
    assert not any(thread.is_alive() for thread in threads), 'socket worker failed to finish'
    assert not failures, failures
    return {'threads': 3, 'calls_per_thread': 30}


def fork_calls():
    import socket
    import _socket_rs as helper
    held = helper.parse_address
    reader = writer = child = None
    primary = None
    try:
        reader, writer = os.pipe()
        child = os.fork()
        if child == 0:
            try:
                os.close(reader)
                for name in NAMES:
                    sys.modules.pop(name, None)
                again = importlib.import_module('socket')
                importlib.reload(again)
                assert held(6, '::1') == again._socket_rs.parse_address(6, '::1')
                roundtrip(again, b'fork')
                os.write(writer, b'PASS')
                os._exit(0)
            except BaseException:
                os._exit(1)
        os.close(writer)
        writer = None
        ready, _, _ = select.select([reader], [], [], 10)
        assert ready and os.read(reader, 4) == b'PASS'
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            observed, status = os.waitpid(child, os.WNOHANG)
            if observed == child:
                child = None
                assert os.waitstatus_to_exitcode(status) == 0
                break
            time.sleep(0.01)
        assert child is None, 'fork child not reaped'
    except BaseException as exc:
        primary = exc
        raise
    finally:
        cleanup_errors = []
        for descriptor in (reader, writer):
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except BaseException as exc:
                    cleanup_errors.append(f'close owned descriptor: {exc!r}')
        if child is not None and child > 0:
            try:
                os.kill(child, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except BaseException as exc:
                cleanup_errors.append(f'kill owned child: {exc!r}')
            # Reaping is attempted even when killing or clock observation fails.
            try:
                observed, status = os.waitpid(child, os.WNOHANG)
                if observed == child:
                    child = None
                else:
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        try:
                            observed, status = os.waitpid(child, os.WNOHANG)
                            if observed == child:
                                child = None
                                break
                        except InterruptedError:
                            continue
                        time.sleep(0.01)
            except ChildProcessError:
                child = None
            except BaseException as exc:
                cleanup_errors.append(f'reap owned child: {exc!r}')
            if child is not None:
                cleanup_errors.append('owned fork child cleanup unresolved')
        if cleanup_errors:
            if primary is not None:
                for message in cleanup_errors:
                    primary.add_note(message)
            else:
                raise AssertionError('; '.join(cleanup_errors))
    return 'PASS'


def own_gil():
    import _interpreters
    results = []
    for _ in range(3):
        reader = writer = interpreter = None
        try:
            reader, writer = os.pipe()
            interpreter = _interpreters.create()
            code = f"""
import importlib, json, os
outcomes = {{}}
for name in ('_socket', '_socket_rs', '_ssl', 'socket', 'ssl'):
    try:
        importlib.import_module(name)
    except ImportError as exc:
        outcomes[name] = [type(exc).__name__, str(exc)]
    else:
        outcomes[name] = 'available'
import socket
assert socket.inet_ntop(socket.AF_INET, socket.inet_pton(socket.AF_INET, '127.0.0.1')) == '127.0.0.1'
left, right = socket.socketpair()
try:
    assert left.send(b'own gil') == 7 and right.recv(7) == b'own gil'
finally:
    left.close(); right.close()
os.write({writer}, json.dumps(outcomes, sort_keys=True).encode())
"""
            assert _interpreters.run_string(interpreter, code) is None
            os.close(writer)
            writer = None
            ready, _, _ = select.select([reader], [], [], 3)
            assert ready, 'interpreter produced no result'
            results.append(json.loads(os.read(reader, 65536)))
        finally:
            if interpreter is not None:
                _interpreters.destroy(interpreter)
            for descriptor in (reader, writer):
                if descriptor is not None:
                    os.close(descriptor)
    assert results[0] == results[1] == results[2]
    return results


def identity(kind, artifact):
    modules = {name: importlib.import_module(name) for name in NAMES}
    paths = {name: Path(module.__file__) for name, module in modules.items()}
    if kind == 'merged':
        assert artifact, 'requires actual Cargo release artifact'
        assert paths['_socket'].is_symlink()
        assert os.readlink(paths['_socket']) == paths['_socket_rs'].name
        assert not paths['_socket_rs'].is_symlink()
        assert paths['_socket'].samefile(paths['_socket_rs'])
        actual = hashlib.sha256(Path(artifact).read_bytes()).hexdigest()
        assert hashlib.sha256(paths['_socket_rs'].read_bytes()).hexdigest() == actual
    else:
        assert not paths['_socket'].is_symlink() and not paths['_socket_rs'].is_symlink()
        assert not paths['_socket'].samefile(paths['_socket_rs'])
    for name, module in modules.items():
        assert module.__spec__.loader.__class__.__name__ == 'ExtensionFileLoader'
        assert name not in sys.builtin_module_names
    return {'kind': kind, 'module_names': list(NAMES)}


PROBES = {
    'direct-c': direct_c, 'direct-helper': direct_helper, 'direct-ssl': direct_ssl,
    'c-first': lambda: import_order(NAMES),
    'rust-first': lambda: import_order(tuple(reversed(NAMES))),
    'unavailable': unavailable_and_partial, 'buffers-retry': buffers_retry_and_timeout,
    'held-generations': held_capsule_generations, 'threads': concurrent_calls,
    'fork': fork_calls, 'own-gil': own_gil,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', choices=[*PROBES, 'kernel-plain', 'kernel-counted', 'identity'], required=True)
    parser.add_argument('--kind', choices=('standalone', 'merged'), required=True)
    parser.add_argument('--artifact')
    parser.add_argument('--kernel-source')
    parser.add_argument('--kernel-sha256')
    parser.add_argument('--reference')
    args = parser.parse_args()
    if args.case == 'identity':
        result = identity(args.kind, args.artifact)
    elif args.case.startswith('kernel-'):
        assert args.kernel_source and args.kernel_sha256
        result = fixed_kernel(args.case.removeprefix('kernel-'), args.kernel_source, args.kernel_sha256)
    else:
        result = PROBES[args.case]()
    normalized = json.loads(json.dumps(result, sort_keys=True))
    if args.reference and args.case != 'identity':
        assert normalized == json.loads(Path(args.reference).read_text())[args.case]
    print(json.dumps({'case': args.case, 'result': normalized}, sort_keys=True))


if __name__ == '__main__':
    main()
