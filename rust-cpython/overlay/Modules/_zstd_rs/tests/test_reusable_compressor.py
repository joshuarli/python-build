"""Compare reusable Rust compressors with the native options-path byte oracle."""

import gc
import unittest

from compression import zstd
import _zstd_rs


class ReusableCompressorTests(unittest.TestCase):
    def setUp(self):
        names = ("encoder_new", "encoder_compress", "encoder_flush", "encoder_set_pledged")
        self.original = {name: getattr(_zstd_rs, name) for name in names}
        self.calls = dict.fromkeys(names, 0)
        for name, method in self.original.items():
            def traced(*args, _name=name, _method=method):
                self.calls[_name] += 1
                return _method(*args)
            setattr(_zstd_rs, name, traced)

    def tearDown(self):
        for name, method in self.original.items():
            setattr(_zstd_rs, name, method)

    def compressors(self, level):
        rust = zstd.ZstdCompressor(level=level)
        native = zstd.ZstdCompressor(options={
            zstd.CompressionParameter.compression_level: level,
        })
        return rust, native

    def assert_frame(self, packet, payload, size):
        self.assertEqual(zstd.decompress(packet), payload)
        info = zstd.get_frame_info(packet)
        self.assertEqual(info.decompressed_size, size)
        self.assertEqual(info.dictionary_id, 0)

    def test_reused_end_frames_preserve_zero_negative_and_extreme_levels(self):
        minimum, maximum = zstd.CompressionParameter.compression_level.bounds()
        levels = (minimum, -5, 0, 3, 9, maximum)
        for level in levels:
            rust, native = self.compressors(level)
            for payload in (bytes(range(256)) * 16, b"small frame" * 29, b""):
                with self.subTest(level=level, size=len(payload)):
                    packet = rust.compress(payload, rust.FLUSH_FRAME)
                    self.assertEqual(packet, native.compress(payload, native.FLUSH_FRAME))
                    self.assert_frame(packet, payload, len(payload))
                    self.assertEqual(rust.last_mode, rust.FLUSH_FRAME)
        self.assertEqual(self.calls["encoder_new"], len(levels))
        self.assertEqual(self.calls["encoder_compress"], len(levels) * 3)

    def test_block_flushes_preserve_partial_history_across_reused_frames(self):
        rust, native = self.compressors(7)
        for suffix in (b"first", b"second", b"third"):
            payload = bytes(range(256)) * 256 + suffix
            operations = (
                ("compress", (payload[:8192], rust.CONTINUE)),
                ("flush", (rust.FLUSH_BLOCK,)),
                ("compress", (payload[8192:16384], rust.FLUSH_BLOCK)),
                ("compress", (payload[16384:], rust.CONTINUE)),
                ("flush", (rust.FLUSH_FRAME,)),
            )
            parts = []
            for method, arguments in operations:
                actual = getattr(rust, method)(*arguments)
                self.assertEqual(actual, getattr(native, method)(*arguments))
                self.assertEqual(rust.last_mode, native.last_mode)
                parts.append(actual)
            self.assert_frame(b"".join(parts), payload, None)
        self.assertEqual(self.calls["encoder_new"], 1)
        self.assertEqual(self.calls["encoder_compress"], 9)
        self.assertEqual(self.calls["encoder_flush"], 6)

    def test_pledged_size_applies_after_recreation_and_resets_after_end(self):
        rust, native = self.compressors(5)
        for size in (8192, 4097):
            payload = (b"pledged frame" * 1000)[:size]
            for compressor in (rust, native):
                compressor.set_pledged_input_size(len(payload))
            packet = rust.compress(payload) + rust.flush()
            self.assertEqual(packet, native.compress(payload) + native.flush())
            self.assert_frame(packet, payload, len(payload))
            unpledged = payload[:127]
            packet = rust.compress(unpledged) + rust.flush()
            self.assertEqual(packet, native.compress(unpledged) + native.flush())
            self.assert_frame(packet, unpledged, None)
        self.assertEqual(self.calls["encoder_new"], 1)
        self.assertEqual(self.calls["encoder_set_pledged"], 2)

    def test_wrong_pledge_resets_a_recreated_context_without_losing_level(self):
        rust, native = self.compressors(-5)
        initial = b"completed frame" * 32
        self.assertEqual(rust.compress(initial, rust.FLUSH_FRAME),
                         native.compress(initial, native.FLUSH_FRAME))
        payload = b"new frame after an error" * 100
        for compressor in (rust, native):
            compressor.set_pledged_input_size(len(payload) - 1)
            compressor.compress(payload[:-1])
            with self.assertRaises(zstd.ZstdError):
                compressor.compress(payload[-1:], compressor.FLUSH_FRAME)
            self.assertEqual(compressor.last_mode, compressor.FLUSH_FRAME)
        packet = rust.compress(payload) + rust.flush()
        self.assertEqual(packet, native.compress(payload) + native.flush())
        self.assert_frame(packet, payload, None)
        for compressor in (rust, native):
            compressor.set_pledged_input_size(len(payload))
        packet = rust.compress(payload, rust.FLUSH_FRAME)
        self.assertEqual(packet, native.compress(payload, native.FLUSH_FRAME))
        self.assert_frame(packet, payload, len(payload))
        self.assertEqual(self.calls["encoder_new"], 1)

    def test_denied_midframe_pledge_keeps_copied_input_and_block_history(self):
        rust, native = self.compressors(3)
        head = bytearray(b"original input" * 300)
        expected = bytes(head) + b"tail"
        parts = [rust.compress(memoryview(head))]
        self.assertEqual(parts[0], native.compress(memoryview(head)))
        head[:] = b"x" * len(head)
        for compressor in (rust, native):
            with self.assertRaises(ValueError):
                compressor.set_pledged_input_size(len(expected))
            self.assertEqual(compressor.last_mode, compressor.CONTINUE)
        parts.append(rust.flush(rust.FLUSH_BLOCK))
        self.assertEqual(parts[-1], native.flush(native.FLUSH_BLOCK))
        for compressor in (rust, native):
            with self.assertRaises(ValueError):
                compressor.set_pledged_input_size(len(expected))
            self.assertEqual(compressor.last_mode, compressor.FLUSH_BLOCK)
        parts.append(rust.compress(b"tail", rust.FLUSH_FRAME))
        self.assertEqual(parts[-1], native.compress(b"tail", native.FLUSH_FRAME))
        self.assert_frame(b"".join(parts), expected, None)
        self.assertEqual(self.calls["encoder_set_pledged"], 0)
        self.assertEqual(self.calls["encoder_new"], 1)

    def test_repeated_empty_frames_and_empty_block_flush_match_native_bytes(self):
        rust, native = self.compressors(4)
        for _ in range(3):
            packet = rust.flush()
            self.assertEqual(packet, native.flush())
            self.assert_frame(packet, b"", 0)
            self.assertEqual(rust.last_mode, rust.FLUSH_FRAME)
        packet = rust.flush(rust.FLUSH_BLOCK)
        self.assertEqual(packet, native.flush(native.FLUSH_BLOCK))
        end = rust.flush()
        self.assertEqual(end, native.flush())
        self.assert_frame(packet + end, b"", None)
        gc.collect()
        self.assertEqual(self.calls["encoder_new"], 1)
        self.assertEqual(self.calls["encoder_flush"], 5)


if __name__ == "__main__":
    unittest.main()
