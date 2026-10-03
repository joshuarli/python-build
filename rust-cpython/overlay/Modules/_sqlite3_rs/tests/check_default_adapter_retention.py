"""Check default adapter message retention and warning binding semantics."""

import ast
import datetime
from pathlib import Path
import sqlite3
import sqlite3.dbapi2 as dbapi
import sys
import warnings
import unittest


MESSAGE = ("The default {what} is deprecated as of Python 3.12; "
           "see the sqlite3 documentation for suggested replacement recipes")


def registered_functions():
    return [
        sqlite3.adapters[(datetime.date, sqlite3.PrepareProtocol)],
        sqlite3.adapters[(datetime.datetime, sqlite3.PrepareProtocol)],
        sqlite3.converters["DATE"],
        sqlite3.converters["TIMESTAMP"],
    ]


class DefaultAdapterRetentionTests(unittest.TestCase):
    def test_only_warning_callable_is_captured(self):
        names = ["adapt_date", "adapt_datetime", "convert_date", "convert_timestamp"]
        for function, name in zip(registered_functions(), names):
            with self.subTest(function=name):
                self.assertEqual(function.__code__.co_freevars, ("warn",))
                self.assertEqual(len(function.__closure__), 1)
                self.assertIs(function.__closure__[0].cell_contents, warnings.warn)
                self.assertIsNone(function.__defaults__)
                self.assertEqual(function.__code__.co_argcount, 1)
                self.assertEqual(function.__qualname__,
                                 "register_adapters_and_converters.<locals>." + name)
                self.assertIn(MESSAGE, function.__code__.co_consts)
        self.assertFalse(hasattr(dbapi, "_warn"))
        self.assertFalse(hasattr(sqlite3, "_warn"))

    def test_captured_warning_ignores_module_rebinding_and_preserves_callsite(self):
        original = warnings.warn

        def rebound(*args, **kwargs):
            raise AssertionError("adapter used a rebound warning callable")

        date = datetime.date(2026, 10, 2)
        stamp = datetime.datetime(2026, 10, 2, 13, 14, 15, 123456)
        arguments = [date, stamp, b"2026-10-02", b"2026-10-02 13:14:15.123456"]
        expected_values = ["2026-10-02", "2026-10-02 13:14:15.123456", date, stamp]
        kinds = ["date adapter", "datetime adapter", "date converter", "timestamp converter"]
        lines = []
        try:
            warnings.warn = rebound
            dbapi._warn = rebound
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", DeprecationWarning)
                for function, argument, expected in zip(registered_functions(), arguments, expected_values):
                    lines.append(sys._getframe().f_lineno + 1)
                    value = function(argument)
                    self.assertEqual(value, expected)
            self.assertEqual(len(caught), 4)
            for warning, kind, line in zip(caught, kinds, lines):
                self.assertIs(warning.category, DeprecationWarning)
                self.assertEqual(str(warning.message), MESSAGE.format(what=kind))
                self.assertEqual(warning.filename, __file__)
                self.assertEqual(warning.lineno, line)
        finally:
            warnings.warn = original
            del dbapi._warn

    def test_regenerated_registration_captures_new_warning_callable(self):
        original = warnings.warn
        originals = registered_functions()
        calls = []

        def rebound(message, category, *, stacklevel):
            calls.append((message, category, stacklevel))

        tree = ast.parse(Path(dbapi.__file__).read_text())
        factory = next(node for node in tree.body
                       if isinstance(node, ast.FunctionDef)
                       and node.name == "register_adapters_and_converters")
        namespace = dict(vars(dbapi))
        exec(compile(ast.Module(body=[factory], type_ignores=[]), dbapi.__file__, "exec"), namespace)
        try:
            warnings.warn = rebound
            namespace["register_adapters_and_converters"]()
            functions = registered_functions()
            for function in functions:
                self.assertIs(function.__closure__[0].cell_contents, rebound)
            warnings.warn = original
            date = datetime.date(2026, 10, 2)
            stamp = datetime.datetime(2026, 10, 2, 13, 14, 15, 123456)
            with sqlite3.connect(":memory:", detect_types=sqlite3.PARSE_COLNAMES) as connection:
                row = connection.execute('select ? as "d [date]", ? as "t [timestamp]"',
                                         (date, stamp)).fetchone()
            self.assertEqual(row, (date, stamp))
            kinds = ["date adapter", "datetime adapter", "date converter", "timestamp converter"]
            self.assertEqual(calls, [(MESSAGE.format(what=kind), DeprecationWarning, 2)
                                     for kind in kinds])
        finally:
            warnings.warn = original
            sqlite3.adapters[(datetime.date, sqlite3.PrepareProtocol)] = originals[0]
            sqlite3.adapters[(datetime.datetime, sqlite3.PrepareProtocol)] = originals[1]
            sqlite3.converters["DATE"] = originals[2]
            sqlite3.converters["TIMESTAMP"] = originals[3]


if __name__ == "__main__":
    unittest.main()
