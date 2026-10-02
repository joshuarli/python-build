"""Check timer deadlines, ready ordering and callback error propagation."""

from collections import deque
import heapq
import unittest

import _asyncio_rs


class Handle:
    def __init__(self, when, *, cancelled=False, callback=None):
        self._when = when
        self._scheduled = True
        self._cancelled = cancelled
        self.callback = callback
        self.runs = 0

    def __lt__(self, other):
        return self._when < other._when

    def _run(self):
        self.runs += 1
        if self.callback is not None:
            self.callback()


class SchedulingContract(unittest.TestCase):
    def test_only_deadlines_before_the_boundary_move_to_ready(self):
        before = Handle(0.5)
        equal = Handle(1.0)
        after = Handle(1.5)
        scheduled = [after, before, equal]
        heapq.heapify(scheduled)
        existing = Handle(-1.0)
        ready = deque([existing])
        result = _asyncio_rs.promote_due_timers(scheduled, ready, 1.0, heapq.heappop)
        self.assertIsNone(result)
        self.assertEqual(list(ready), [existing, before])
        self.assertIs(before._scheduled, False)
        self.assertIs(equal._scheduled, True)
        self.assertIs(after._scheduled, True)
        self.assertEqual(set(scheduled), {equal, after})

    def test_pop_ready_transfers_the_first_handle_and_preserves_empty_error(self):
        first = Handle(0)
        second = Handle(1)
        ready = deque([first, second])
        self.assertIs(_asyncio_rs.pop_ready_handle(ready), first)
        self.assertEqual(list(ready), [second])
        self.assertIs(_asyncio_rs.pop_ready_handle(ready), second)
        with self.assertRaises(IndexError):
            _asyncio_rs.pop_ready_handle(ready)

    def test_dispatch_pops_cancelled_handles_without_running_them(self):
        cancelled = Handle(0, cancelled=True)
        active = Handle(1)
        ready = deque([cancelled, active])
        self.assertIsNone(_asyncio_rs.dispatch_ready_handle(ready))
        self.assertEqual(cancelled.runs, 0)
        self.assertEqual(list(ready), [active])
        self.assertIsNone(_asyncio_rs.dispatch_ready_handle(ready))
        self.assertEqual(active.runs, 1)
        self.assertFalse(ready)

    def test_callback_exception_keeps_identity_and_consumes_the_handle(self):
        error = RuntimeError('callback failed')

        def fail():
            raise error

        handle = Handle(0, callback=fail)
        ready = deque([handle])
        with self.assertRaises(RuntimeError) as caught:
            _asyncio_rs.dispatch_ready_handle(ready)
        self.assertIs(caught.exception, error)
        self.assertEqual(handle.runs, 1)
        self.assertFalse(ready)

    def test_arity_errors_keep_the_native_messages(self):
        cases = (
            (_asyncio_rs.promote_due_timers, 'promote_due_timers requires four arguments'),
            (_asyncio_rs.pop_ready_handle, 'pop_ready_handle requires one argument'),
            (_asyncio_rs.dispatch_ready_handle, 'dispatch_ready_handle requires one argument'),
        )
        for function, message in cases:
            with self.subTest(function=function.__name__):
                with self.assertRaisesRegex(TypeError, '^' + message + '$'):
                    function()


if __name__ == '__main__':
    unittest.main()
