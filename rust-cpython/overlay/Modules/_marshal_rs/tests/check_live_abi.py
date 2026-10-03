"""Exercise marshal's capsule through a pinned-header native observer."""
import importlib.util
import marshal
import sys
import unittest
import _marshal_rs

spec = importlib.util.spec_from_file_location("_marshal_abi_test", sys.argv.pop(1))
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


class MarshalLiveAbiTests(unittest.TestCase):
    def assert_codec(self, value):
        # Two explicit owners make FLAG_REF independent of call scaffolding.
        owners = (value, value)
        expected = marshal.dumps(owners[0], 6)
        handled, record = observer.dumps(_marshal_rs, owners[1], 1)
        self.assertTrue(handled)
        self.assertEqual(record, expected)
        handled, decoded = observer.loads(_marshal_rs, record, 1)
        self.assertTrue(handled)
        self.assertEqual(decoded, value)
        return decoded

    def test_live_capsule_and_module_slots(self):
        self.assertIsNone(observer.module_contract(_marshal_rs))
        self.assertEqual(observer.loads(_marshal_rs, b"N", 1), (True, None))

    def test_literal_wire_records_independent_of_public_dispatch(self):
        cases = [(None, b"N"), (False, b"F"), (True, b"T"),
                 (0x12345678, b"\xe9\x78\x56\x34\x12"),
                 (-0x12345678, b"\xe9\x88\xa9\xcb\xed"),
                 (1.25, b"\xe7\0\0\0\0\0\0\xf4\x3f"),
                 (b"abc", b"\xf3\x03\0\0\0abc"),
                 (2**63, b"\xec\x05\0\0\0" + b"\0\0" * 4 + b"\x08\0")]
        for value, expected in cases:
            with self.subTest(value=value):
                owners = (value, value)
                self.assertEqual(observer.dumps(_marshal_rs, owners[0], 1), (True, expected))
                self.assertEqual(observer.loads(_marshal_rs, expected, 1), (True, owners[1]))

    def test_object_and_container_fields(self):
        values = [0, -1, 17, 1.25, (), (1, "item"), [], [1, "item"]]
        for value in values:
            with self.subTest(value=value):
                self.assertIsNone(observer.live_fields(value))
                self.assert_codec(value)

    def test_long_export_and_writer_boundaries(self):
        for value in [0, 2**30 - 1, 2**30, 2**31 - 1, 2**31,
                      2**63 - 1, 2**63, 2**4096 + 2**177 + 1]:
            for signed in [value, -value]:
                with self.subTest(value=signed):
                    self.assertIsNone(observer.live_fields(signed))
                    self.assert_codec(signed)

    def test_string_bytes_float_and_complex_signatures(self):
        values = [False, True, None, b"", bytes(range(256)) * 30,
                  "", "a" * 255, "a" * 256, "λ日本", "\ud800",
                  sys.intern("marshal_interned_abi"), -0.0, 1.25, complex(1.25, -3.5)]
        for value in values:
            with self.subTest(value=type(value).__name__):
                self.assert_codec(value)

    def test_dict_set_and_reference_identity(self):
        shared = [2**200, "shared"]
        value = {"left": shared, "right": shared, "set": {3, 1, 2},
                 "frozen": frozenset({1, 2, 3})}
        decoded = self.assert_codec(value)
        self.assertIs(decoded["left"], decoded["right"])

    def test_list_and_tuple_backreferences(self):
        cyclic = []
        cyclic.append(cyclic)
        owners = (cyclic, cyclic)
        handled, record = observer.dumps(_marshal_rs, owners[0], 1)
        self.assertTrue(handled)
        self.assertEqual(record, marshal.dumps(owners[1], 6))
        handled, decoded = observer.loads(_marshal_rs, record, 1)
        self.assertTrue(handled)
        self.assertIs(decoded[0], decoded)
        inner = []
        outer = (inner,)
        inner.append(outer)
        handled, record = observer.dumps(_marshal_rs, outer, 1)
        self.assertTrue(handled)
        self.assertEqual(record, marshal.dumps(outer, 6))
        handled, decoded = observer.loads(_marshal_rs, record, 1)
        self.assertTrue(handled)
        self.assertIs(decoded[0][0], decoded)

    def test_code_parts_and_allow_code_rejection(self):
        code = compile("def f(x, /, *, y=3):\n    return x + y\n", "marshal-abi", "exec")
        decoded = self.assert_codec(code)
        namespace = {}
        exec(decoded, namespace)
        self.assertEqual(namespace["f"](4, y=7), 11)
        self.assertEqual(observer.dumps(_marshal_rs, code, 0), (False, None))
        self.assertEqual(observer.loads(_marshal_rs, marshal.dumps(code, 6), 0), (False, None))
        with self.assertRaisesRegex(ValueError, "^marshalling code objects is disallowed$"):
            marshal.dumps(code, 6, allow_code=False)
        with self.assertRaisesRegex(ValueError, "^unmarshalling code objects is disallowed$"):
            marshal.loads(marshal.dumps(code, 6), allow_code=False)

    def test_rejected_records_clear_errors_and_drop_partial_objects(self):
        for record in [b"", b"?", b"0", b"r\xff\xff\xff\x7f", b"[\x01\0\0\0?",
                       b"\xdb\x01\0\0\0?", b"l\xff\xff\xff\x7f"]:
            with self.subTest(record=record):
                self.assertEqual(observer.loads(_marshal_rs, record, 1), (False, None))
                self.assert_codec([2**100, "after rejection"])
        self.assertEqual(observer.dumps(_marshal_rs, object(), 1), (False, None))
        # Slice records are accepted by the public C fallback, while the
        # capsule reports that its own codec does not handle them.
        value = slice(1, 7, 2)
        self.assertEqual(observer.dumps(_marshal_rs, value, 1), (False, None))
        self.assertEqual(marshal.loads(marshal.dumps(value, 6)), value)

    def test_mem_allocation_rejection_restores_allocator(self):
        value = [2**300, "shared"]
        record = marshal.dumps(value, 6)
        for _ in range(3):
            self.assertGreater(observer.memory_rejection(_marshal_rs, value, 0), 0)
            self.assertGreater(observer.memory_rejection(_marshal_rs, record, 1), 0)
            self.assert_codec(value)


if __name__ == "__main__":
    unittest.main()
