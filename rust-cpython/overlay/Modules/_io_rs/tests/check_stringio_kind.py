"""Public StringIO contracts across writes, realization, and Unicode ranges."""
import io
import pickle
import sys
import unittest


class StringIOContracts(unittest.TestCase):
    def test_overwrites_preserve_character_positions_tail_and_snapshots(self):
        stream = io.StringIO('ascii-tail')
        snapshots = [stream.getvalue()]
        expected = snapshots[0]
        for replacement in ('A', '\xe9', '\u6f22', '\U0001f642'):
            stream.seek(1)
            self.assertEqual(stream.write(replacement), 1)
            self.assertEqual(stream.tell(), 2)
            expected = expected[:1] + replacement + expected[2:]
            self.assertEqual(stream.getvalue(), expected)
            stream.seek(0)
            self.assertEqual(stream.read(3), expected[:3])
            snapshots.append(stream.getvalue())
        self.assertEqual(snapshots, ['ascii-tail', 'aAcii-tail', 'a\xe9cii-tail',
                                     'a\u6f22cii-tail', 'a\U0001f642cii-tail'])
        stream.close()
        self.assertEqual(snapshots[-1], expected)

    def test_gaps_truncate_and_growing_writes_count_characters(self):
        for text in ('abc', '\xe9bc', '\u6f22bc', '\U0001f642bc'):
            with self.subTest(text=text):
                stream = io.StringIO(text)
                stream.seek(6)
                self.assertEqual(stream.write('\U0001f642'), 1)
                self.assertEqual(stream.getvalue(), text + '\0' * 3 + '\U0001f642')
                self.assertEqual(stream.tell(), 7)
                self.assertEqual(stream.truncate(4), 4)
                self.assertEqual(stream.tell(), 7)
                self.assertEqual(stream.getvalue(), text + '\0')
                self.assertEqual(stream.truncate(10), 10)
                self.assertEqual(stream.getvalue(), text + '\0')
                stream.seek(1)
                self.assertEqual(stream.truncate(), 1)
                self.assertEqual(stream.getvalue(), text[:1])
                payload = '\u6f22\U0001f642' * 200
                self.assertEqual(stream.write(payload), len(payload))
                self.assertEqual(stream.getvalue(), text[:1] + payload)

    def test_newline_read_readline_and_iteration(self):
        raw = '\xe9\n\u6f22\r\n\U0001f642\rZ'
        cases = (
            (None, '\xe9\n\u6f22\n\U0001f642\nZ', ['\xe9\n', '\u6f22\n', '\U0001f642\n', 'Z']),
            ('', raw, ['\xe9\n', '\u6f22\r\n', '\U0001f642\r', 'Z']),
            ('\n', raw, ['\xe9\n', '\u6f22\r\n', '\U0001f642\rZ']),
            ('\r', '\xe9\r\u6f22\r\r\U0001f642\rZ', ['\xe9\r', '\u6f22\r', '\r', '\U0001f642\r', 'Z']),
            ('\r\n', '\xe9\r\n\u6f22\r\r\n\U0001f642\rZ', ['\xe9\r\n', '\u6f22\r\r\n', '\U0001f642\rZ']),
        )
        for newline, value, lines in cases:
            with self.subTest(newline=newline):
                stream = io.StringIO(newline=newline)
                self.assertEqual(stream.write(raw), len(raw))
                self.assertEqual(stream.getvalue(), value)
                stream.seek(0)
                self.assertEqual(stream.read(1), value[:1])
                self.assertEqual(stream.read(), value[1:])
                stream.seek(0)
                self.assertEqual([stream.readline() for _ in lines], lines)
                self.assertEqual(stream.readline(), '')
                stream.seek(0)
                self.assertEqual(list(stream), lines)
                stream.seek(0)
                self.assertEqual(stream.readline(1), '\xe9')
                self.assertEqual(stream.tell(), 1)

    def test_state_restores_raw_newlines_without_translating_twice(self):
        raw = '\xe9\r\n\u6f22\r\U0001f642\n'
        for newline in ('', '\n', '\r', '\r\n'):
            with self.subTest(newline=newline):
                stream = io.StringIO('old')
                stream.__setstate__((raw, newline, 2, {'tag': 'restored'}))
                self.assertEqual(stream.getvalue(), raw)
                self.assertEqual(stream.tell(), 2)
                self.assertEqual(stream.tag, 'restored')
                self.assertEqual(stream.__getstate__(), (raw, newline, 2, {'tag': 'restored'}))
                for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
                    if protocol < 2:
                        with self.assertRaises(TypeError) as caught:
                            pickle.dumps(stream, protocol)
                        self.assertIs(type(caught.exception), TypeError)
                        continue
                    restored = pickle.loads(pickle.dumps(stream, protocol))
                    self.assertEqual(restored.getvalue(), raw)
                    self.assertEqual(restored.tell(), 2)
                    self.assertEqual(restored.tag, 'restored')
                    restored.seek(0)
                    self.assertEqual(restored.read(), raw)

    def test_reinitialization_reopens_and_replaces_content(self):
        stream = io.StringIO('\U0001f642-tail', newline='')
        stream.seek(1)
        stream.write('\u6f22')
        snapshot = stream.getvalue()
        stream.close()
        stream.__init__('ascii\r\n', newline=None)
        self.assertFalse(stream.closed)
        self.assertEqual(stream.tell(), 0)
        self.assertEqual(stream.getvalue(), 'ascii\n')
        stream.__init__('\xe9\u6f22\U0001f642', newline='\n')
        self.assertEqual(stream.read(), '\xe9\u6f22\U0001f642')
        self.assertEqual(snapshot, '\U0001f642\u6f22tail')

    def test_subclass_unicode_data_and_method_dispatch(self):
        class Text(str):
            def __str__(self):
                raise AssertionError('write must use Unicode data')
        class Stream(io.StringIO):
            def readline(self, *args):
                line = super().readline(*args)
                return 'override:' + line if line else line
        stream = Stream()
        stream.write(Text('ascii\n'))
        stream.seek(0)
        stream.write(Text('\U0001f642'))
        self.assertEqual(stream.getvalue(), '\U0001f642scii\n')
        stream.seek(0)
        self.assertEqual(stream.readline(), 'override:\U0001f642scii\n')
        stream.seek(0)
        self.assertEqual(list(stream), ['override:\U0001f642scii\n'])

    def test_extreme_positions_and_exact_error_classes(self):
        stream = io.StringIO('\xe9\u6f22\U0001f642')
        stream.seek(1)
        stream.write('x')
        snapshot = stream.getvalue()
        stream.seek(sys.maxsize)
        for read in (stream.read, stream.readline):
            self.assertEqual(read(), '')
            self.assertEqual(stream.tell(), sys.maxsize)
        self.assertEqual(list(stream), [])
        for position, error in ((sys.maxsize, OverflowError),
                                (sys.maxsize // 2 + 16, OverflowError),
                                (sys.maxsize // 4 + 16, MemoryError)):
            stream.seek(position)
            with self.assertRaises(error) as caught:
                stream.write('x')
            self.assertIs(type(caught.exception), error)
            self.assertEqual(stream.tell(), position)
            self.assertEqual(stream.getvalue(), snapshot)
        for operation, error in ((lambda: stream.seek(-1), ValueError),
                                 (lambda: stream.seek(1, 1), OSError),
                                 (lambda: stream.truncate(-1), ValueError),
                                 (lambda: stream.write(b'x'), TypeError)):
            with self.assertRaises(error) as caught:
                operation()
            self.assertIs(type(caught.exception), error)
        stream.close()
        with self.assertRaises(ValueError):
            stream.getvalue()


if __name__ == '__main__':
    unittest.main()
