"""Check Future transitions, Rust routing, and waiter reference lifetimes."""

from concurrent.futures import Future
from concurrent.futures import _base
import _concurrent_futures_rs as native
import unittest


class CoreOnlyTransitionTests(unittest.TestCase):
    def test_completion_notifies_waiters_added_during_notification(self):
        future = Future()
        value = object()
        events = []
        callback_values = []

        class Later:
            def add_result(self, completed):
                events.append(("later", completed.result()))

        class First:
            def add_result(self, completed):
                events.append(("first", completed.result()))
                completed._waiters.append(Later())

        future._waiters.append(First())
        future.add_done_callback(lambda completed: callback_values.append(completed.result()))
        original = native.set_result
        routed = []

        def record(*args):
            routed.append(args)
            return original(*args)

        try:
            native.set_result = record
            self.assertTrue(future.set_running_or_notify_cancel())
            future.set_result(value)
        finally:
            native.set_result = original
        self.assertEqual([event[0] for event in events], ["first", "later"])
        self.assertTrue(all(event[1] is value for event in events))
        self.assertEqual(callback_values, [value])
        self.assertEqual(len(routed), 1)
        self.assertIs(routed[0][0], future)
        self.assertIs(routed[0][1], value)
        self.assertEqual(routed[0][2], _base.FINISHED)
        self.assertTrue(future.done())

    def test_cancel_and_exception_notify_the_correct_waiter_method(self):
        events = []

        class Waiter:
            def add_cancelled(self, future):
                events.append(("cancel", future))

            def add_exception(self, future):
                events.append(("exception", future))

        cancelled = Future()
        cancelled._waiters.append(Waiter())
        self.assertTrue(cancelled.cancel())
        self.assertFalse(cancelled.set_running_or_notify_cancel())
        self.assertEqual(cancelled._state, _base.CANCELLED_AND_NOTIFIED)
        failed = Future()
        failed._waiters.append(Waiter())
        error = ValueError("future failure")
        failed.set_exception(error)
        self.assertIs(failed.exception(), error)
        self.assertEqual(events, [("cancel", cancelled), ("exception", failed)])
        with self.assertRaises(ValueError) as raised:
            failed.result()
        self.assertIs(raised.exception, error)

    def test_waiter_error_preserves_completed_result_and_propagates(self):
        future = Future()
        value = object()
        error = ValueError("waiter failure")

        class FailingWaiter:
            def add_result(self, completed):
                raise error

        future._waiters.append(FailingWaiter())
        with self.assertRaises(ValueError) as raised:
            future.set_result(value)
        self.assertIs(raised.exception, error)
        self.assertEqual(future._state, _base.FINISHED)
        self.assertIs(future.result(), value)

    def test_native_arity_errors_remain_python_exceptions(self):
        for function in (native.set_result, native.set_exception):
            with self.subTest(function=function.__name__):
                with self.assertRaisesRegex(TypeError, "future completion requires three arguments"):
                    function()
        with self.assertRaisesRegex(TypeError, "future scheduling transition requires five arguments"):
            native.set_running_or_notify_cancel()


if __name__ == "__main__":
    unittest.main()
