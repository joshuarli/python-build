"""Run alone in a fresh GIL-enabled process with the typed C probe installed."""
import io
import unittest
import _stringio_reset_allocator as probe


class StringIOResetAllocationTests(unittest.TestCase):
    def test_discarded_accumulated_text_needs_no_whole_content_buffer(self):
        # A matching name does not confer the native type/module association.
        spoof = type("_io.StringIO", (io.StringIO,), {})()
        before = probe.last_stats()
        with self.assertRaises(TypeError):
            probe.reset(spoof.truncate, 1)
        self.assertEqual(probe.last_stats(), before)

        calls = []

        class Override(io.StringIO):
            def truncate(self, position):
                calls.append(position)
                return 0

        with self.assertRaises(TypeError):
            probe.reset(Override().truncate, 1)
        self.assertEqual(calls, [])
        self.assertEqual(probe.last_stats(), before)
        with self.assertRaises(TypeError):
            probe.reset(io.StringIO().read, 1)
        self.assertEqual(probe.last_stats(), before)
        shadowed = io.StringIO("unchanged")
        shadowed.truncate = shadowed.read
        with self.assertRaises(TypeError):
            probe.reset(shadowed.truncate, 1)
        self.assertEqual(probe.last_stats(), before)
        self.assertEqual((shadowed.getvalue(), shadowed.tell()), ("unchanged", 0))

        stream = io.StringIO()
        text = "ascii" * 32768
        stream.write(text)
        held = stream.getvalue()
        stream.seek(0)
        # Only MEM realloc requests at least the discarded UCS4 payload are
        # rejected. Python object allocation and small reset metadata stay live.
        result, calls, maximum, rejected = probe.reset(stream.truncate, len(text) * 4)
        self.assertEqual(result, 0)
        self.assertEqual(rejected, 0)
        self.assertLess(maximum, len(text) * 4)
        self.assertEqual((stream.getvalue(), stream.tell()), ("", 0))
        stream.write("replacement")
        self.assertEqual(stream.getvalue(), "replacement")
        self.assertEqual(held, text)

    def test_failed_buffer_shrink_preserves_realized_text_and_cursor(self):
        stream = io.StringIO("original" * 4096)
        stream.seek(1)
        stream.write("X")  # Existing overwrite realizes the UCS4 buffer.
        held = stream.getvalue()
        position = stream.tell()
        with self.assertRaises(MemoryError):
            probe.reset(stream.truncate, 1)
        self.assertGreater(probe.last_stats()[2], 0)
        self.assertEqual((stream.getvalue(), stream.tell()), (held, position))
        self.assertEqual(stream.truncate(0), 0)
        self.assertEqual(stream.tell(), position)
        stream.write("ok")
        self.assertEqual(stream.getvalue(), "\0" * position + "ok")


if __name__ == "__main__":
    unittest.main()
