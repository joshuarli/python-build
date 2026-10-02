"""Exercise the actual fixture cleanup with owned fake descriptors and PID."""
import ast
import os
from pathlib import Path
import select
import signal
import sys
import time
import types
import unittest
from unittest.mock import Mock, patch


class SocketForkCleanupContracts(unittest.TestCase):
    def invoke(self, *, primary, close_fault=None, kill_fault=None, unresolved=False):
        source = Path(__file__).parents[1] / 'overlay/Modules/_socket_rs/tests/test_socket_c_image.py'
        tree = ast.parse(source.read_text())
        function = next(node for node in tree.body
                        if isinstance(node, ast.FunctionDef) and node.name == 'fork_calls')
        fake_os = types.SimpleNamespace(
            pipe=Mock(return_value=(101, 102)), fork=Mock(return_value=4242),
            close=Mock(side_effect=[None, close_fault] if close_fault else None),
            kill=Mock(side_effect=kill_fault),
            waitpid=Mock(return_value=(0, 0) if unresolved else (4242, 0)),
            WNOHANG=os.WNOHANG)
        ticks = iter(range(100))
        fake_time = types.SimpleNamespace(monotonic=lambda: next(ticks), sleep=Mock())
        namespace = {'os': fake_os, 'sys': sys, 'select': types.SimpleNamespace(
                     select=Mock(side_effect=primary)), 'signal': signal,
                     'time': fake_time, 'NAMES': ('_socket', '_socket_rs')}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
        fake_socket = types.ModuleType('socket')
        fake_helper = types.ModuleType('_socket_rs')
        fake_helper.parse_address = Mock()
        with patch.dict(sys.modules, {'socket': fake_socket, '_socket_rs': fake_helper}):
            with self.assertRaises(type(primary)) as caught:
                namespace['fork_calls']()
        self.assertIs(caught.exception, primary)
        fake_os.kill.assert_called_once_with(4242, signal.SIGKILL)
        self.assertGreater(fake_os.waitpid.call_count, 0)
        fake_os.waitpid.assert_called_with(4242, os.WNOHANG)
        self.assertEqual(fake_os.close.call_args_list[-1].args, (101,))
        return getattr(primary, '__notes__', [])

    def test_primary_failure_survives_close_and_kill_baseexceptions(self):
        notes = self.invoke(primary=ValueError('original select failure'),
                            close_fault=KeyboardInterrupt('close fault'),
                            kill_fault=SystemExit('kill fault'))
        self.assertTrue(any('close owned descriptor' in note for note in notes))
        self.assertTrue(any('kill owned child' in note for note in notes))
        self.assertFalse(any('unresolved' in note for note in notes))

    def test_kill_failure_still_reaps_owned_child(self):
        notes = self.invoke(primary=AssertionError('original failure'),
                            kill_fault=KeyboardInterrupt('kill interrupted'))
        self.assertEqual(len(notes), 1)
        self.assertIn('kill owned child', notes[0])

    def test_unresolved_owned_pid_is_not_hidden(self):
        notes = self.invoke(primary=RuntimeError('original failure'), unresolved=True)
        self.assertIn('owned fork child cleanup unresolved', notes)


if __name__ == '__main__':
    unittest.main()
