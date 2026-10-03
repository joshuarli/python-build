"""Cold context resolution preserves native launch errors and registration order."""
import sys

if 'threading' in sys.modules or '_contextvars' in sys.modules:
    raise RuntimeError('fixture requires a fresh threading/contextvars namespace')

import threading

worker = threading.Thread(target=lambda: values.append('unexpected worker'))
values = []
launch_failure = RuntimeError('injected native launch failure')
pending_at_resolution = []
launch_calls = []


class ResettingContextFinder:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == '_contextvars':
            with threading._active_limbo_lock:
                pending_at_resolution.append(worker in threading._limbo)
                threading._limbo.pop(worker, None)
        return None


def failing_launch(*args, **kwargs):
    launch_calls.append((args, kwargs))
    raise launch_failure


# unittest imports warnings, which activates context variables. Exercise the
# cold import before that framework initialization and retain its outcome.
finder = ResettingContextFinder()
original = threading._start_joinable_thread
captured = None
sys.meta_path.insert(0, finder)
try:
    assert '_contextvars' not in sys.modules
    assert original is sys.modules['_thread'].start_joinable_thread
    threading._start_joinable_thread = failing_launch
    try:
        worker.start()
    except BaseException as error:
        captured = (error, error.__traceback__)
finally:
    threading._start_joinable_thread = original
    sys.meta_path.remove(finder)

import unittest


class SuccessfulContextResolutionTests(unittest.TestCase):
    def test_successful_resolution_reset_preserves_native_launch_exception(self):
        with self.assertRaises(RuntimeError) as caught:
            if captured is None:
                self.fail('native launch did not propagate an exception')
            raise captured[0].with_traceback(captured[1])
        self.assertIs(caught.exception, launch_failure)
        self.assertEqual(pending_at_resolution, [False])
        self.assertEqual(launch_calls, [((worker._bootstrap,), {
            'handle': worker._os_thread_handle, 'daemon': worker.daemon})])
        with threading._active_limbo_lock:
            self.assertNotIn(worker, threading._limbo)
        self.assertFalse(worker._started.is_set())
        self.assertIsNone(worker.ident)
        self.assertEqual(values, [])
        self.assertIn('_contextvars', sys.modules)


if __name__ == '__main__':
    unittest.main()
