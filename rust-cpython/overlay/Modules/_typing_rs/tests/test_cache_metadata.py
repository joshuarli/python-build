"""Public typing wrappers retain semantics without private LRU metadata copies."""
import functools
import importlib
import inspect
import threading
import typing
import unittest


class TypingCacheMetadataTests(unittest.TestCase):
    def decorate(self, function, *, typed=False):
        wrapped = typing._tp_cache(function, typed=typed)
        cache = typing._caches[function]
        callback = next(clear for clear in typing._cleanups
                        if getattr(clear, '__self__', None) is cache)

        def release():
            callback()
            if typing._caches.get(function) is cache:
                del typing._caches[function]
            for index, clear in enumerate(typing._cleanups):
                if clear is callback:
                    del typing._cleanups[index]
                    break

        self.addCleanup(release)
        return wrapped, cache, callback

    def test_private_cache_has_no_duplicate_metadata_owner(self):
        def original(value):
            return value
        wrapped, cache, clear = self.decorate(original)
        self.assertNotIn('__wrapped__', vars(cache))
        self.assertNotIn('cache_parameters', vars(cache))
        self.assertIs(wrapped.__wrapped__, original)
        self.assertIs(clear.__self__, cache)
        self.assertEqual(cache.cache_info(), (0, 0, 128, 0))

    def test_public_wrapper_metadata_and_signature_are_unchanged(self):
        def original(value: int = 3, *, flag: bool = False) -> tuple:
            """Return the original values."""
            return value, flag
        original.marker = object()
        wrapped, cache, clear = self.decorate(original)
        for name in functools.WRAPPER_ASSIGNMENTS:
            if hasattr(original, name):
                self.assertEqual(getattr(wrapped, name), getattr(original, name))
        self.assertIs(wrapped.marker, original.marker)
        self.assertIs(wrapped.__wrapped__, original)
        self.assertIs(inspect.unwrap(wrapped), original)
        self.assertEqual(inspect.signature(wrapped), inspect.signature(original))
        self.assertEqual(wrapped(7, flag=True), (7, True))
        self.assertIs(clear.__self__, cache)

    def test_typed_keys_cache_identity_and_clear_remain(self):
        calls = []
        def original(value):
            result = object()
            calls.append((value, result))
            return result
        wrapped, cache, clear = self.decorate(original, typed=True)
        integer = wrapped(1)
        floating = wrapped(1.0)
        self.assertIs(wrapped(1), integer)
        self.assertIs(wrapped(1.0), floating)
        self.assertIsNot(integer, floating)
        self.assertEqual(len(calls), 2)
        clear()
        self.assertEqual(cache.cache_info(), (0, 0, 128, 0))
        self.assertIsNot(wrapped(1), integer)

    def test_unhashable_and_function_typeerrors_keep_original_call_order(self):
        calls = []
        def original(value):
            calls.append(value)
            if value == 'error':
                raise TypeError('original error')
            return value
        wrapped, cache, clear = self.decorate(original)
        value = [1, 2]
        self.assertIs(wrapped(value), value)
        self.assertEqual(calls, [value])
        with self.assertRaisesRegex(TypeError, 'original error'):
            wrapped('error')
        self.assertEqual(calls, [value, 'error', 'error'])
        self.assertEqual(cache.cache_info().currsize, 0)

    def test_hash_reentry_and_clear_during_call_remain_safe(self):
        calls = []
        def original(value):
            calls.append(value)
            if value == 'clear':
                clear()
            return object()
        wrapped, cache, clear = self.decorate(original)
        nested = wrapped('nested')
        class Key:
            def __hash__(self):
                self_result = wrapped('nested')
                if self_result is not nested:
                    raise AssertionError('reentrant cache identity changed')
                return 42
        key = Key()
        first = wrapped(key)
        self.assertIs(wrapped(key), first)
        self.assertIs(wrapped('clear'), wrapped('clear'))
        self.assertIs(wrapped('after'), wrapped('after'))
        self.assertEqual(sum(value is key for value in calls), 1)
        self.assertLessEqual(cache.cache_info().currsize, 128)

    def test_two_bounded_workers_preserve_results_and_cache_operations(self):
        def original(value):
            return (value, value * 2)
        wrapped, cache, clear = self.decorate(original, typed=True)
        barrier = threading.Barrier(3, timeout=10)
        failures = []
        results = []
        def consume(value):
            try:
                barrier.wait()
                for _ in range(20):
                    results.append(wrapped(value))
                    if wrapped(value) != (value, value * 2):
                        raise AssertionError('worker result changed')
            except BaseException as error:
                failures.append(error)
        workers = [threading.Thread(target=consume, args=(value,), daemon=True)
                   for value in (3, 5)]
        started = []
        primary = None
        join_errors = []
        try:
            for worker in workers:
                started.append(worker)
                worker.start()
            barrier.wait()
        except BaseException as error:
            primary = error
        finally:
            for worker in started:
                try:
                    worker.join(timeout=15)
                except BaseException as error:
                    join_errors.append(error)
        if primary is not None:
            for error in join_errors:
                primary.add_note(f'worker join failed: {error!r}')
            raise primary
        self.assertEqual(join_errors, [], 'worker join failed')
        self.assertFalse(any(worker.is_alive() for worker in workers), 'worker did not finish')
        self.assertEqual(failures, [])
        self.assertEqual(results.count((3, 6)), 20)
        self.assertEqual(results.count((5, 10)), 20)
        self.assertIs(wrapped(3), wrapped(3))
        clear()
        self.assertEqual(cache.cache_info(), (0, 0, 128, 0))

    def test_public_aliases_keep_rust_origin_and_argument_dispatch(self):
        import _typing_rs
        originals = {name: getattr(_typing_rs, name) for name in ('get_origin', 'get_args')}
        calls = {name: 0 for name in originals}
        def forwarding(name):
            def call(*args):
                calls[name] += 1
                return originals[name](*args)
            return call
        try:
            for name in originals:
                setattr(_typing_rs, name, forwarding(name))
            aliases = (list[int], typing.Optional[int], typing.Callable[[int], str],
                       typing.Literal['a', 'b'], typing.Annotated[int, 'meta'])
            origins = tuple(typing.get_origin(alias) for alias in aliases)
            arguments = tuple(typing.get_args(alias) for alias in aliases)
            self.assertEqual(origins, (list, typing.Union, __import__('collections').abc.Callable,
                                       typing.Literal, typing.Annotated))
            self.assertEqual(arguments, ((int,), (int, type(None)), ([int], str),
                                         ('a', 'b'), (int, 'meta')))
            self.assertEqual(calls, {'get_origin': 5, 'get_args': 5})
        finally:
            for name, method in originals.items():
                setattr(_typing_rs, name, method)

    def test_z_reload_preserves_held_clear_owner_and_old_lookup_behavior(self):
        def original(value):
            return object()
        wrapped, cache, clear = self.decorate(original)
        wrapped(1)
        self.assertEqual(cache.cache_info().currsize, 1)
        importlib.reload(typing)
        clear()
        self.assertEqual(cache.cache_info(), (0, 0, 128, 0))
        with self.assertRaises(KeyError):
            wrapped(1)
        self.assertEqual(typing.get_args(typing.Literal['fresh']), ('fresh',))


if __name__ == '__main__':
    unittest.main()
