"""Thread context import and selection contracts in a fresh fixture process."""
import sys

if 'threading' in sys.modules or '_contextvars' in sys.modules:
    raise RuntimeError('fixture requires a fresh threading/contextvars namespace')

import threading


def cold_synchronization():
    assert '_contextvars' not in sys.modules
    import _threading_rs
    original = _threading_rs._barrier_transition
    transitions = []

    def recording_transition(*args):
        result = original(*args)
        transitions.append(args)
        return result

    try:
        _threading_rs._barrier_transition = recording_transition
        barrier = threading.Barrier(1)
        assert barrier.wait() == 0
        assert barrier.n_waiting == 0
        assert transitions
    finally:
        _threading_rs._barrier_transition = original
    assert '_contextvars' not in sys.modules


def cold_failure_and_retry():
    assert '_contextvars' not in sys.modules
    failures = (ImportError('injected deferred context import failure'),
                KeyboardInterrupt('injected deferred context import interruption'),
                ImportError('injected failure after pending registration reset'))
    failure = failures[0]

    class FailingContextFinder:
        def find_spec(self, fullname, path=None, target=None):
            if fullname == '_contextvars':
                if failure is failures[-1]:
                    # Reentrant import code can reset pending registrations.
                    with threading._active_limbo_lock:
                        threading._limbo.pop(worker, None)
                raise failure
            return None

    finder = FailingContextFinder()
    values = []
    worker = threading.Thread(target=lambda: values.append('_contextvars' in sys.modules))
    sys.meta_path.insert(0, finder)
    try:
        for failure in failures:
            caught = None
            try:
                worker.start()
            except BaseException as error:
                caught = error
            assert caught is failure
            with threading._active_limbo_lock:
                assert worker not in threading._limbo
            assert not worker._started.is_set()
            assert worker.ident is None
            assert values == []
            assert worker._context is None
            assert '_contextvars' not in sys.modules
    finally:
        sys.meta_path.remove(finder)

    started = False
    try:
        worker.start()
        started = True
    finally:
        if started:
            worker.join(5)
            assert not worker.is_alive(), 'context activation worker did not terminate'
    assert values == [True]


# The test framework imports warnings, which activates the context module.
# Capture the cold operations first and report their outcomes as real tests.
cold_outcomes = {}
for name, operation in (('synchronization', cold_synchronization),
                        ('failure_and_retry', cold_failure_and_retry)):
    try:
        operation()
    except BaseException as error:
        cold_outcomes[name] = (error, error.__traceback__)
    else:
        cold_outcomes[name] = None

import unittest


class DeferredThreadContextTests(unittest.TestCase):
    def test_00_synchronization_keeps_context_module_deferred(self):
        outcome = cold_outcomes['synchronization']
        if outcome is not None:
            raise outcome[0].with_traceback(outcome[1])

    def test_01_failed_context_import_leaves_no_registration_and_allows_retry(self):
        outcome = cold_outcomes['failure_and_retry']
        if outcome is not None:
            raise outcome[0].with_traceback(outcome[1])

    def test_02_default_context_selection_on_start(self):
        import _contextvars
        variable = _contextvars.ContextVar('threading-deferred-context')
        variable.set('caller')
        values = []
        worker = threading.Thread(target=lambda: values.append(variable.get('empty')))
        started = False
        try:
            worker.start()
            started = True
        finally:
            if started:
                worker.join(5)
                self.assertFalse(worker.is_alive(), 'context worker did not terminate')
        expected = 'caller' if sys.flags.thread_inherit_context else 'empty'
        self.assertEqual(values, [expected])
        self.assertEqual(variable.get(), 'caller')

    def test_03_explicit_context_remains_the_selected_context(self):
        import _contextvars
        variable = _contextvars.ContextVar('threading-explicit-context')
        context = _contextvars.Context()
        context.run(variable.set, 'explicit')
        values = []
        worker = threading.Thread(
            context=context, target=lambda: values.append(variable.get('empty')))
        started = False
        try:
            worker.start()
            started = True
        finally:
            if started:
                worker.join(5)
                self.assertFalse(worker.is_alive(), 'explicit context worker did not terminate')
        self.assertEqual(values, ['explicit'])
        self.assertEqual(context.run(variable.get), 'explicit')


if __name__ == '__main__':
    unittest.main()
