"""Helper activation and callback contracts using fresh wrapper namespaces."""
import builtins
import contextlib
import importlib.util
import pathlib
import sys
import threading
import types
import unittest


SOURCE = pathlib.Path(contextlib.__file__).read_text()
FILENAME = contextlib.__file__
MISSING = object()


def fresh():
    module = types.ModuleType('_contextlib_activation_fixture')
    module.__file__ = FILENAME
    module.__spec__ = importlib.util.spec_from_file_location(module.__name__, FILENAME)
    exec(compile(SOURCE, FILENAME, 'exec'), module.__dict__)
    return module


def complete(coroutine):
    try:
        value = coroutine.send(None)
    except StopIteration as result:
        return result.value
    else:
        coroutine.close()
        raise AssertionError(f'fixed coroutine unexpectedly suspended: {value!r}')


class NativeCalls:
    def __init__(self, native):
        self.native = native
        self.calls = []

    def push_callback(self, *args):
        self.calls.append('push')
        return self.native.push_callback(*args)

    def pop_callback(self, *args):
        self.calls.append('pop')
        return self.native.pop_callback(*args)

    def wrap_callback(self, *args):
        self.calls.append('wrap')
        return self.native.wrap_callback(*args)


class HelperActivation(unittest.TestCase):
    def setUp(self):
        self.saved_import = builtins.__import__
        self.saved_helper = sys.modules.pop('_contextlib_rs', MISSING)

    def tearDown(self):
        builtins.__import__ = self.saved_import
        if self.saved_helper is MISSING:
            sys.modules.pop('_contextlib_rs', None)
        else:
            sys.modules['_contextlib_rs'] = self.saved_helper

    def native(self):
        native = self.saved_import('_contextlib_rs')
        for name in ('push_callback', 'pop_callback', 'wrap_callback'):
            function = getattr(native, name)
            self.assertIs(type(function), types.BuiltinFunctionType)
            self.assertIs(function.__self__, native)
            self.assertEqual(function.__module__, '_contextlib_rs')
        return native

    def test_non_stack_contexts_do_not_activate_helper(self):
        calls = []

        def observed(name, *args, **kwargs):
            if name == '_contextlib_rs':
                calls.append(name)
            return self.saved_import(name, *args, **kwargs)

        builtins.__import__ = observed
        module = fresh()
        self.assertNotIn('_contextlib_rs', sys.modules)
        with module.suppress(ValueError):
            raise ValueError('suppressed')
        closed = []
        item = types.SimpleNamespace(close=lambda: closed.append(True))
        with module.closing(item) as held:
            self.assertIs(held, item)

        @module.contextmanager
        def managed():
            yield 17

        @module.asynccontextmanager
        async def async_managed():
            yield 19

        with managed() as value:
            self.assertEqual(value, 17)

        async def use_async():
            async with async_managed() as value:
                return value

        self.assertEqual(complete(use_async()), 19)
        self.assertEqual(closed, [True])
        self.assertEqual(calls, [])
        self.assertNotIn('_contextlib_rs', sys.modules)

    def test_first_stack_call_activates_native_and_all_three_routes(self):
        module = fresh()
        self.assertNotIn('_contextlib_rs', sys.modules)
        values = []
        stack = module.ExitStack()
        stack.callback(values.append, 'first')
        self.assertIn('_contextlib_rs', sys.modules)
        native = self.native()
        self.assertIs(module.__dict__['_contextlib_rs'], native)
        calls = NativeCalls(native)
        module._contextlib_rs = calls
        stack.callback(values.append, 'second')
        stack.close()
        self.assertEqual(values, ['second', 'first'])
        self.assertEqual(calls.calls, ['push', 'pop', 'wrap', 'pop', 'wrap'])

    def test_override_before_activation_and_reload_with_held_stack(self):
        module = fresh()
        native = self.native()
        override = NativeCalls(native)
        module._contextlib_rs = override
        values = []
        stack = module.ExitStack()
        stack.callback(values.append, 'held')
        self.assertEqual(override.calls, ['push'])
        exec(compile(SOURCE, FILENAME, 'exec'), module.__dict__)
        second = NativeCalls(native)
        module._contextlib_rs = second
        stack.close()
        self.assertEqual(values, ['held'])
        self.assertEqual(override.calls, ['push'])
        self.assertEqual(second.calls, ['pop', 'wrap'])

    def test_import_failure_occurs_at_stack_use_and_can_retry(self):
        attempts = []

        def unavailable(name, *args, **kwargs):
            if name == '_contextlib_rs':
                attempts.append(name)
                raise ImportError('unavailable contextlib helper')
            return self.saved_import(name, *args, **kwargs)

        builtins.__import__ = unavailable
        module = fresh()
        stack = module.ExitStack()
        with self.assertRaisesRegex(ImportError, 'unavailable contextlib helper'):
            stack.callback(lambda: None)
        self.assertEqual(len(stack._exit_callbacks), 0)
        self.assertEqual(attempts, ['_contextlib_rs'])
        builtins.__import__ = self.saved_import
        values = []
        stack.callback(values.append, 'retried')
        stack.close()
        self.assertEqual(values, ['retried'])
        self.assertIs(module.__dict__['_contextlib_rs'], self.native())
        held = module.ExitStack()
        held.callback(values.append, 'held through failed unwind')
        exec(compile(SOURCE, FILENAME, 'exec'), module.__dict__)
        sys.modules.pop('_contextlib_rs', None)
        builtins.__import__ = unavailable
        with self.assertRaisesRegex(ImportError, 'unavailable contextlib helper'):
            held.close()
        self.assertEqual(len(held._exit_callbacks), 1)
        self.assertEqual(values, ['retried'])
        builtins.__import__ = self.saved_import
        held.close()
        self.assertEqual(values, ['retried', 'held through failed unwind'])

    def test_reentrant_import_publishes_backend_before_nested_stack_use(self):
        module = fresh()
        values = []
        entered = []

        def importing(name, *args, **kwargs):
            if name == '_contextlib_rs' and not entered:
                entered.append(True)
                native = self.saved_import(name, *args, **kwargs)
                module._contextlib_rs = native
                with module.ExitStack() as nested:
                    nested.callback(values.append, 'nested')
                return native
            return self.saved_import(name, *args, **kwargs)

        builtins.__import__ = importing
        with module.ExitStack() as stack:
            stack.callback(values.append, 'outer')
        self.assertEqual(entered, [True])
        self.assertEqual(values, ['nested', 'outer'])
        self.assertIs(module.__dict__['_contextlib_rs'], self.native())

    def test_two_threads_first_use_publish_one_native_module(self):
        module = fresh()
        barrier = threading.Barrier(2)
        values = [None, None]
        failures = []

        def worker(index):
            try:
                barrier.wait(timeout=5)
                with module.ExitStack() as stack:
                    stack.callback(lambda: values.__setitem__(index, index))
            except BaseException as error:
                failures.append(error)

        workers = [threading.Thread(target=worker, args=(index,)) for index in range(2)]
        try:
            for worker_thread in workers:
                worker_thread.start()
        finally:
            for worker_thread in workers:
                if worker_thread.ident is not None:
                    worker_thread.join(timeout=10)
            self.assertFalse(any(worker_thread.is_alive() for worker_thread in workers))
        self.assertEqual(failures, [])
        self.assertEqual(values, [0, 1])
        self.assertIs(module.__dict__['_contextlib_rs'], self.native())

    def test_sync_async_lifo_suppression_and_exception_context(self):
        module = fresh()
        calls = NativeCalls(self.native())
        module._contextlib_rs = calls
        values = []
        with module.ExitStack() as stack:
            stack.callback(values.append, 'oldest')
            stack.push(lambda *exc: values.append('suppress') or True)
            stack.callback(values.append, 'newest')
            raise ValueError('suppressed')
        self.assertEqual(values, ['newest', 'suppress', 'oldest'])
        self.assertEqual(calls.calls, ['push'] * 3 + ['pop', 'wrap'] * 3)
        values.clear()
        calls.calls.clear()

        async def async_exit(*exc):
            values.append('async-suppress')
            return True

        async def async_callback():
            values.append('async-last')

        async def use_async():
            async with module.AsyncExitStack() as stack:
                stack.callback(values.append, 'sync-oldest')
                stack.push_async_exit(async_exit)
                stack.push_async_callback(async_callback)
                raise KeyError('suppressed')

        complete(use_async())
        self.assertEqual(values, ['async-last', 'async-suppress', 'sync-oldest'])
        self.assertEqual(calls.calls, ['push'] * 3 + ['pop', 'wrap'] * 3)

        def replacement(*exc):
            raise RuntimeError('replacement')

        original = ValueError('original')
        try:
            with module.ExitStack() as stack:
                stack.push(replacement)
                raise original
        except RuntimeError as error:
            self.assertIs(error.__context__, original)
        else:
            self.fail('replacement exception was swallowed')

    def test_own_gil_interpreter_uses_native_after_lazy_activation(self):
        import _interpreters
        interpreter = _interpreters.create('isolated')
        try:
            self.assertEqual(_interpreters.get_config(interpreter).gil, 'own')
            self.assertIsNone(_interpreters.run_string(interpreter, """
import sys
import contextlib
assert '_contextlib_rs' not in sys.modules
values = []
with contextlib.ExitStack() as stack:
    stack.callback(values.append, 17)
assert values == [17]
backend = contextlib._contextlib_rs
for name in ('push_callback', 'pop_callback', 'wrap_callback'):
    function = getattr(backend, name)
    assert type(function).__name__ == 'builtin_function_or_method'
    assert function.__self__ is backend
    assert function.__module__ == '_contextlib_rs'
"""))
        except BaseException as primary:
            try:
                _interpreters.destroy(interpreter)
            except BaseException as cleanup:
                primary.add_note(f'interpreter destruction also failed: {cleanup!r}')
            raise
        else:
            _interpreters.destroy(interpreter)


if __name__ == '__main__':
    unittest.main()
