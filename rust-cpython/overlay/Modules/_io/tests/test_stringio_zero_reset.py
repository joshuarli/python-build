"""Observable StringIO reset contracts, with an optional allocation oracle."""
import io
import pickle
import unittest


class StringIOZeroResetTests(unittest.TestCase):
    def test_subclasses_keep_write_content_without_str_conversion(self):
        class Stream(io.StringIO):
            pass

        class Text(str):
            def __str__(self):
                raise AssertionError("StringIO.write must not convert a str subclass")

        stream = Stream()
        for text in (Text("before"), Text("after\u0100")):
            stream.seek(0)
            stream.truncate(0)
            self.assertEqual(stream.write(text), len(text))
            self.assertEqual(stream.getvalue(), text[:])

    def test_repeated_reset_preserves_held_results_and_unicode(self):
        stream = io.StringIO()
        held = []
        for text in ("ascii\0text", "\u0100\u03b1", "\U0001f642", "again" * 4096):
            stream.seek(0)
            self.assertEqual(stream.truncate(), 0)
            self.assertEqual(stream.tell(), 0)
            self.assertEqual(stream.write(text), len(text))
            held.append((stream.getvalue(), text))
            self.assertEqual(stream.read(), "")
        for result, expected in held:
            self.assertEqual(result, expected)

    def test_zero_truncate_keeps_cursor_and_gap_write(self):
        for text in ("abcd", "\U0001f642abcd"):
            stream = io.StringIO(text)
            stream.seek(7)
            self.assertEqual(stream.truncate(0), 0)
            self.assertEqual(stream.tell(), 7)
            self.assertEqual(stream.getvalue(), "")
            self.assertEqual(stream.write("\u0100"), 1)
            self.assertEqual(stream.getvalue(), "\0" * 7 + "\u0100")
            stream.seek(0)
            self.assertEqual(stream.read(), "\0" * 7 + "\u0100")

    def test_newline_history_and_policy_survive_reset(self):
        for newline in (None, "", "\n", "\r", "\r\n"):
            stream = io.StringIO(newline=newline)
            stream.write("a\r\nb\rc\n")
            history = stream.newlines
            stream.seek(0)
            stream.truncate(0)
            self.assertEqual(stream.newlines, history)
            stream.write("d\ne\r\n")
            # A fresh stream determines the configured write translation.
            fresh = io.StringIO(newline=newline)
            fresh.write("d\ne\r\n")
            self.assertEqual(stream.getvalue(), fresh.getvalue())
            stream.seek(0)
            fresh.seek(0)
            self.assertEqual(stream.readlines(), fresh.readlines())

    def test_pickle_and_reentrant_index_conversion(self):
        stream = io.StringIO("before")

        class Position:
            def __index__(self):
                stream.seek(0)
                stream.write("after!")
                stream.seek(3)
                return 0

        self.assertEqual(stream.truncate(Position()), 0)
        self.assertEqual(stream.tell(), 3)
        for protocol in range(2, pickle.HIGHEST_PROTOCOL + 1):
            clone = pickle.loads(pickle.dumps(stream, protocol))
            self.assertEqual(clone.getvalue(), "")
            self.assertEqual(clone.tell(), 3)
            clone.write("x")
            self.assertEqual(clone.getvalue(), "\0\0\0x")
        stream.__init__("reinitialized")
        self.assertEqual(stream.getvalue(), "reinitialized")

    def test_invalid_requests_and_closed_stream_keep_errors(self):
        stream = io.StringIO("unchanged")
        stream.seek(2)
        with self.assertRaises(ValueError):
            stream.truncate(-1)
        with self.assertRaises(TypeError):
            stream.truncate(1.5)
        self.assertEqual((stream.getvalue(), stream.tell()), ("unchanged", 2))
        stream.close()
        with self.assertRaises(ValueError):
            stream.truncate(0)


if __name__ == "__main__":
    unittest.main()
