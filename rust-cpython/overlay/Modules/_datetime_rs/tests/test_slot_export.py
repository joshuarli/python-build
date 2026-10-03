"""Observable method, module-lifetime, and public-route contracts."""
import datetime
import importlib
import sys
import threading
import unittest

import _datetime
import _datetime_rs as native


NAMES = ("parse_date", "parse_time", "format_date", "format_time",
         "format_datetime", "add_date", "add_datetime")


class SlotExportTests(unittest.TestCase):
    def test_seven_methods_metadata_results_and_errors(self):
        for name in NAMES:
            method = getattr(native, name)
            self.assertEqual(method.__name__, name)
            self.assertEqual(method.__module__, "_datetime_rs")
            self.assertIs(method.__self__, native)
            self.assertIsNone(method.__doc__)
            with self.assertRaises(TypeError):
                method()
            with self.assertRaises(TypeError):
                method(unexpected=1)
        self.assertEqual(native.__doc__, "Rust datetime field operations.")
        self.assertEqual(native.parse_date("2024-02-29"), (2024, 2, 29))
        self.assertEqual(native.parse_date("2023-02-29"), ())
        self.assertEqual(native.parse_time("T12:34:56.123456"), (12, 34, 56, 123456))
        self.assertEqual(native.parse_time("24:00:00"), ())
        fields = (-(2**63), 2**63-1, -1)
        self.assertEqual(native.format_date(*fields),
                         f"{fields[0]:04}-{fields[1]:02}-{fields[2]:02}")
        self.assertEqual(native.format_time(1, 2, 3, 456789, 4), "01:02:03.456789")
        self.assertEqual(native.format_time(1, 2, 3, 456789, 99), ())
        self.assertEqual(native.format_datetime(2024, 2, 29, 1, 2, 3, 0, ord("\U0001f600"), 2),
                         "2024-02-29\U0001f60001:02:03")
        self.assertEqual(native.add_date(2024, 2, 28, 1), (2024, 2, 29))
        self.assertEqual(native.add_datetime(2024, 2, 29, 23, 59, 59, 999999,
                                            0, 0, 1, 1), (2024, 3, 1, 0, 0, 0, 0))

    def test_exception_identity_and_reentrant_integer_conversion(self):
        marker = RuntimeError("datetime integer conversion sentinel")

        class BadIndex:
            def __index__(self):
                raise marker

        with self.assertRaises(RuntimeError) as raised:
            native.format_date(BadIndex(), 1, 1)
        self.assertIs(raised.exception, marker)

        class ReentrantIndex:
            def __index__(self):
                self.parts = native.parse_date("2024-02-29")
                return self.parts[0]

        index = ReentrantIndex()
        self.assertEqual(native.format_date(index, 1, 2), "2024-01-02")
        self.assertEqual(index.parts, (2024, 2, 29))
        with self.assertRaises(UnicodeEncodeError):
            native.parse_date("\ud800")
        with self.assertRaises(OverflowError):
            native.format_date(2**100, 1, 1)

    def test_public_dispatch_monkeypatch_restore_and_native_capsule(self):
        self.assertIs(datetime.date, _datetime.date)
        self.assertIs(datetime.datetime, _datetime.datetime)
        self.assertEqual(type(_datetime.datetime_CAPI).__name__, "PyCapsule")
        original = {name: getattr(native, name) for name in NAMES}
        calls = []

        def wrap(name):
            def call(*args):
                calls.append(name)
                return original[name](*args)
            return call

        try:
            for name in NAMES:
                setattr(native, name, wrap(name))
            self.assertEqual(datetime.date.fromisoformat("2024-02-29"), datetime.date(2024, 2, 29))
            self.assertEqual(datetime.time.fromisoformat("12:34:56"), datetime.time(12, 34, 56))
            self.assertEqual(datetime.date(2024, 2, 29).isoformat(), "2024-02-29")
            self.assertEqual(datetime.time(1, 2, 3).isoformat(), "01:02:03")
            self.assertEqual(datetime.datetime(2024, 2, 29).isoformat(), "2024-02-29T00:00:00")
            self.assertEqual(datetime.date(2024, 2, 28) + datetime.timedelta(days=1),
                             datetime.date(2024, 2, 29))
            self.assertEqual(datetime.datetime(2024, 2, 29) + datetime.timedelta(days=1),
                             datetime.datetime(2024, 3, 1))
            self.assertEqual(set(calls), set(NAMES))
        finally:
            for name, method in original.items():
                setattr(native, name, method)
        before = _datetime.datetime_CAPI
        try:
            sys.modules["_datetime_rs"] = None
            self.assertEqual(datetime.date.fromisoformat("2024-02-29"), datetime.date(2024, 2, 29))
            self.assertEqual(datetime.datetime(2024, 2, 29).isoformat(), "2024-02-29T00:00:00")
        finally:
            sys.modules["_datetime_rs"] = native
        self.assertIs(_datetime.datetime_CAPI, before)

    def test_reload_and_thread_transfer_keep_retained_callables_live(self):
        methods = tuple(getattr(native, name) for name in NAMES)
        self.assertIs(importlib.reload(native), native)
        self.assertEqual(tuple(getattr(native, name) for name in NAMES), methods)
        baseline = sys.getrefcount(native)
        failures = []

        def worker():
            try:
                self.assertEqual(methods[0]("2024-02-29"), (2024, 2, 29))
                self.assertEqual(methods[2](2024, 2, 29), "2024-02-29")
                self.assertTrue(all(method.__self__ is sys.modules["_datetime_rs"] for method in methods))
            except BaseException as error:
                failures.append((type(error).__name__, str(error)))

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(10)
        self.assertFalse(thread.is_alive(), "datetime worker did not finish")
        self.assertEqual(failures, [])
        self.assertEqual(methods[0]("2024-02-29"), (2024, 2, 29))
        self.assertEqual(sys.getrefcount(native), baseline)


if __name__ == "__main__":
    unittest.main()
