import sqlite3
import unittest

import _sqlite3_rs


class SQLiteDelegateTests(unittest.TestCase):
    def test_execute_preserves_step_delegate_exception_and_recovers(self):
        original = _sqlite3_rs.step
        connection = sqlite3.connect(':memory:')
        sentinel = RuntimeError('step delegate failed')
        calls = []

        def failing(statement):
            calls.append(statement)
            raise sentinel

        try:
            _sqlite3_rs.step = failing
            try:
                with self.assertRaises(RuntimeError) as caught:
                    connection.execute('select 42')
                self.assertIs(caught.exception, sentinel)
                self.assertEqual(len(calls), 1)
            finally:
                _sqlite3_rs.step = original
            self.assertEqual(connection.execute('select 43').fetchone(), (43,))
        finally:
            _sqlite3_rs.step = original
            connection.close()

    def test_execute_preserves_invalid_step_result_error_and_recovers(self):
        original = _sqlite3_rs.step
        connection = sqlite3.connect(':memory:')
        calls = []

        def invalid(statement):
            calls.append(statement)
            return object()

        try:
            _sqlite3_rs.step = invalid
            try:
                with self.assertRaises(TypeError):
                    connection.execute('select 42')
                self.assertEqual(len(calls), 1)
            finally:
                _sqlite3_rs.step = original
            self.assertEqual(connection.execute('select 43').fetchone(), (43,))
        finally:
            _sqlite3_rs.step = original
            connection.close()

    def test_sql_callback_failure_keeps_database_error_policy(self):
        connection = sqlite3.connect(':memory:')
        calls = []

        def failing():
            calls.append(None)
            raise RuntimeError('SQL callback failed')

        try:
            connection.create_function('failing', 0, failing)
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute('select failing()')
            self.assertEqual(len(calls), 1)
            self.assertEqual(connection.execute('select 43').fetchone(), (43,))
        finally:
            connection.close()


if __name__ == '__main__':
    unittest.main()
