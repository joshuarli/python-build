"""Observable callback contracts for the Rust contextlib route."""
import contextlib
import gc
import unittest
import weakref

import _contextlib_rs


class ContextlibCoreCallbacksTests(unittest.TestCase):
    def test_stack_uses_replaceable_append_and_pop_providers(self):
        marker = object()
        calls = []

        class Callbacks:
            def append(self, callback):
                calls.append(('append', callback))
                return marker

            def pop(self):
                calls.append(('pop',))
                return marker

        callbacks = Callbacks()
        callback = object()
        self.assertIs(_contextlib_rs.push_callback(callbacks, callback), marker)
        self.assertIs(_contextlib_rs.pop_callback(callbacks), marker)
        self.assertEqual(calls, [('append', callback), ('pop',)])

    def test_provider_exception_identity_survives_dispatch(self):
        error = RuntimeError('append provider failed')

        class Callbacks:
            def append(self, callback):
                raise error

        with self.assertRaises(RuntimeError) as raised:
            _contextlib_rs.push_callback(Callbacks(), object())
        self.assertIs(raised.exception, error)

    def test_callback_result_and_arguments_preserve_identity(self):
        marker = object()
        argument = object()
        calls = []

        def callback(value):
            calls.append(value)
            return marker

        wrapped = _contextlib_rs.wrap_callback(callback, False)
        self.assertIs(wrapped(argument), marker)
        self.assertIs(calls[0], argument)

    def test_suppression_truth_exception_preserves_identity(self):
        error = ValueError('suppression truth failed')

        class Result:
            def __bool__(self):
                raise error

        wrapped = _contextlib_rs.wrap_callback(lambda: Result(), True)
        with self.assertRaises(ValueError) as raised:
            wrapped()
        self.assertIs(raised.exception, error)

    def test_wrapper_retains_callback_until_destruction(self):
        class Callback:
            def __call__(self):
                return None

        callback = Callback()
        reference = weakref.ref(callback)
        wrapped = _contextlib_rs.wrap_callback(callback, False)
        del callback
        gc.collect()
        self.assertIsNotNone(reference())
        wrapped()
        del wrapped
        gc.collect()
        self.assertIsNone(reference())

    def test_public_exit_stack_order_and_exception_suppression(self):
        events = []

        def suppress(exc_type, exc, traceback):
            events.append(('suppress', exc_type, exc))
            return True

        error = RuntimeError('body')
        with contextlib.ExitStack() as stack:
            stack.callback(events.append, 'first')
            stack.push(suppress)
            raise error
        self.assertEqual(events, [('suppress', RuntimeError, error), 'first'])


if __name__ == '__main__':
    unittest.main()
