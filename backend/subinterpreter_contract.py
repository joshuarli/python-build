import gc
import sys
from concurrent import interpreters
from concurrent.futures import InterpreterPoolExecutor
from pathlib import Path

import rtls

root = Path(__file__).parent.resolve()
certdata = str(Path(sys.argv[1]).resolve())
expression = f"(__import__('sys').path.insert(0, {str(root)!r}), __import__('subinterpreter_worker').run({certdata!r}))[1]"
expected = ('TLSv1.2', 'rejected', 'TLSv1.3', 'rejected')
def check_native_ownership():
    native = rtls._rustls
    initial = native._library.rtls_native_handle_count()

    def fail(*arguments, **keywords):
        raise MemoryError("injected binding allocation failure")

    for owner, name in ((native, "_Reply"), (native.ctypes, "create_string_buffer"), (native, "_decode"), (native.weakref, "finalize")):
        original = getattr(owner, name)
        setattr(owner, name, fail)
        try:
            try:
                native.RustlsConfigBuilder()
            except MemoryError:
                pass
            else:
                raise AssertionError("allocation failure did not reach the caller")
        finally:
            setattr(owner, name, original)
        assert native._library.rtls_native_handle_count() == initial

    original = native._library.rtls_native_invoke

    def interrupt_after_native_call(*arguments):
        original(*arguments)
        raise KeyboardInterrupt("injected handoff interruption")

    native._library.rtls_native_invoke = interrupt_after_native_call
    try:
        try:
            native.RustlsConfigBuilder()
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError("handoff interruption did not reach the caller")
    finally:
        native._library.rtls_native_invoke = original
    assert native._library.rtls_native_handle_count() == initial

    builder = native.RustlsConfigBuilder()
    try:
        try:
            builder.set_ech_configs(b"unsupported")
        except NotImplementedError:
            pass
        else:
            raise AssertionError("unsupported ECH configuration was accepted")
        assert builder.has_ech() is False
    finally:
        builder.close()
    try:
        builder.root_cert_count()
    except RuntimeError:
        pass
    else:
        raise AssertionError("a released handle remained usable")
    assert native._library.rtls_native_handle_count() == initial
    assert native.rand_bytes(0) == b""
    assert len(native.rand_bytes(65553)) == 65553


check_native_ownership()
initial = rtls._rustls._library.rtls_native_handle_count()
for iteration in range(3):
    workers = [interpreters.create(), interpreters.create()]
    try:
        for worker in workers:
            worker.exec(f'assert eval({expression!r}) == {expected!r}')
        print('round', iteration, 'interpreters', [worker.id for worker in workers])
    finally:
        for worker in workers:
            worker.close()
    gc.collect()
    observed = rtls._rustls._library.rtls_native_handle_count()
    assert observed == initial, (initial, observed)
with InterpreterPoolExecutor(2) as executor:
    futures = [executor.submit(eval, expression) for _ in range(4)]
    assert [future.result() for future in futures] == [expected] * 4
gc.collect()
observed = rtls._rustls._library.rtls_native_handle_count()
assert observed == initial, (initial, observed)
print('executor TLS and native teardown passed', initial)
