"""Temporary creation callbacks preserve retries, errors and owned results."""
import gc
import types
import unittest
import weakref

import _tempfile_rs


class TempfileRuntimeContractTests(unittest.TestCase):
    def environment(self, **changes):
        events = []
        path = types.SimpleNamespace(
            join=lambda directory, name: directory + "/" + name,
            abspath=lambda name: "absolute:" + name,
            isdir=lambda directory: True,
        )
        os = types.SimpleNamespace(name="posix", path=path)
        os.__dict__.update(changes)
        audit = types.SimpleNamespace(audit=lambda *args: events.append(args))
        return os, audit, events

    def create_file(self, os, audit, names=("a",), attempts=1):
        return _tempfile_rs.mkstemp_inner(
            "directory", "prefix-", ".suffix", 123, iter(names), os,
            audit, attempts, 17, next,
        )

    def create_directory(self, os, audit, names=("a",), attempts=1):
        return _tempfile_rs.mkdtemp(
            "directory", "prefix-", ".suffix", iter(names), os,
            audit, attempts, 17, next,
        )

    def test_collision_retries_audit_each_candidate_and_keep_modes(self):
        calls = []
        def open_file(path, flags, mode):
            calls.append((path, flags, mode))
            if len(calls) == 1:
                raise FileExistsError("occupied")
            return 42
        os, audit, events = self.environment(open=open_file)
        self.assertEqual(self.create_file(os, audit, ("a", "b"), 2),
                         (42, "directory/prefix-b.suffix"))
        self.assertEqual(calls, [("directory/prefix-a.suffix", 123, 0o600),
                                 ("directory/prefix-b.suffix", 123, 0o600)])
        self.assertEqual(events, [("tempfile.mkstemp", row[0]) for row in calls])

    def test_audit_error_identity_prevents_creation(self):
        error = RuntimeError("audit denied")
        calls = []
        os, audit, _ = self.environment(open=lambda *args: calls.append(args))
        def deny(*args):
            raise error
        audit.audit = deny
        with self.assertRaises(RuntimeError) as caught:
            self.create_file(os, audit)
        self.assertIs(caught.exception, error)
        self.assertEqual(calls, [])

    def test_windows_permission_retry_restores_final_exception_identity(self):
        errors = [PermissionError("first"), PermissionError("last")]
        calls = []
        def mkdir(path, mode):
            calls.append((path, mode))
            raise errors[len(calls) - 1]
        os, audit, events = self.environment(name="nt", mkdir=mkdir)
        with self.assertRaises(PermissionError) as caught:
            self.create_directory(os, audit, ("a", "b"), 2)
        self.assertIs(caught.exception, errors[-1])
        self.assertEqual([mode for _, mode in calls], [0o700, 0o700])
        self.assertEqual(len(events), 2)

    def test_exhaustion_and_iterator_errors_keep_arguments(self):
        os, audit, events = self.environment()
        with self.assertRaises(FileExistsError) as caught:
            self.create_file(os, audit, attempts=0)
        self.assertEqual(caught.exception.args,
                         (17, "No usable temporary file name found"))
        with self.assertRaises(FileExistsError) as caught:
            self.create_directory(os, audit, attempts=-1)
        self.assertEqual(caught.exception.args,
                         (17, "No usable temporary directory name found"))
        with self.assertRaises(StopIteration):
            self.create_file(os, audit, names=())
        self.assertEqual(events, [])

    def test_reentrant_callback_and_temporary_results_release_references(self):
        class Result:
            pass
        released = []
        def mkdir(path, mode):
            result = Result()
            released.append(weakref.ref(result))
            return result
        inner_os, inner_audit, _ = self.environment(mkdir=mkdir)
        nested = []
        def open_file(path, flags, mode):
            nested.append(self.create_directory(inner_os, inner_audit))
            return Result()
        os, audit, _ = self.environment(open=open_file)
        result = self.create_file(os, audit)
        held = weakref.ref(result[0])
        gc.collect()
        self.assertEqual(nested, ["absolute:directory/prefix-a.suffix"])
        self.assertIsNone(released[0]())
        self.assertIsNotNone(held())
        del result
        gc.collect()
        self.assertIsNone(held())

    def test_function_owner_and_wrong_arity_remain_exact(self):
        for function, message in [
            (_tempfile_rs.mkstemp_inner, "mkstemp_inner expects 10 arguments"),
            (_tempfile_rs.mkdtemp, "mkdtemp expects 9 arguments"),
        ]:
            self.assertEqual(function.__module__, "_tempfile_rs")
            with self.assertRaises(TypeError) as caught:
                function()
            self.assertEqual(caught.exception.args, (message,))


if __name__ == "__main__":
    unittest.main()
