"""Native logging message callbacks preserve order, errors and record fields."""
import importlib
import logging
import unittest

import _logging_rs


class CoreMessageTests(unittest.TestCase):
    def test_message_truth_and_remainder_callbacks_run_in_order(self):
        events = []
        class Text(str):
            def __mod__(self, args):
                events.append(("remainder", args))
                return "formatted"
        class Message:
            def __str__(self):
                events.append("str")
                return Text("%s")
        class Arguments:
            def __bool__(self):
                events.append("bool")
                return True
        args = Arguments()
        self.assertEqual(_logging_rs.get_message(Message(), args), "formatted")
        self.assertEqual(events, ["str", "bool", ("remainder", args)])
        events.clear()
        self.assertEqual(_logging_rs.get_message(Message(), ()), "%s")
        self.assertEqual(events, ["str"])
        self.assertEqual(_logging_rs.get_message("%(value)s", {"value": "α\0😀"}), "α\0😀")

    def test_errors_keep_identity_and_stop_later_callbacks(self):
        for failure in ("str", "bool", "remainder"):
            with self.subTest(failure=failure):
                error = LookupError(failure)
                events = []
                class Text(str):
                    def __mod__(self, args):
                        events.append("remainder")
                        if failure == "remainder":
                            raise error
                        return "formatted"
                class Message:
                    def __str__(self):
                        events.append("str")
                        if failure == "str":
                            raise error
                        return Text("%s")
                class Arguments:
                    def __bool__(self):
                        events.append("bool")
                        if failure == "bool":
                            raise error
                        return True
                with self.assertRaises(LookupError) as caught:
                    _logging_rs.get_message(Message(), Arguments())
                self.assertIs(caught.exception, error)
                self.assertEqual(events, ["str", "bool", "remainder"][:
                                 {"str": 1, "bool": 2, "remainder": 3}[failure]])
        for args in ((), ("one",), ("one", (), "extra")):
            with self.assertRaisesRegex(TypeError, "^get_message requires a message and its arguments$"):
                _logging_rs.get_message(*args)
        self.assertEqual(_logging_rs.get_message("still usable", ()), "still usable")

    def test_public_record_keeps_native_dispatch_and_record_fields(self):
        original = _logging_rs.get_message
        calls = []
        def forwarding(message, args):
            calls.append((message, args))
            return original(message, args)
        record = logging.LogRecord("core", logging.INFO, "source.py", 23,
                                   "%s", ("value",), None, "caller")
        try:
            _logging_rs.get_message = forwarding
            self.assertEqual(record.getMessage(), "value")
            self.assertEqual(calls, [("%s", ("value",))])
            self.assertEqual((record.pathname, record.lineno, record.funcName),
                             ("source.py", 23, "caller"))
            self.assertEqual((record.msg, record.args), ("%s", ("value",)))
        finally:
            _logging_rs.get_message = original

    def test_reload_keeps_held_native_callable(self):
        held = _logging_rs.get_message
        self.assertIs(importlib.reload(_logging_rs), _logging_rs)
        self.assertEqual(held("%s", ("held",)), "held")
        self.assertEqual(_logging_rs.get_message("%s", ("current",)), "current")


if __name__ == "__main__":
    unittest.main()
