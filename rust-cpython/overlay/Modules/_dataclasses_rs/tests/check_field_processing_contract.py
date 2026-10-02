"""Observable contracts for native ordered field processing."""

import unittest
import weakref

import _dataclasses_rs


class Field:
    def __init__(self, name):
        self.name = name


class FieldProcessingContractTests(unittest.TestCase):
    def test_merge_and_set_preserve_destination_identity_and_override_order(self):
        first = Field("first")
        second = Field("second")
        replacement = Field("first")
        destination = {}
        self.assertIs(
            _dataclasses_rs.merge_fields(destination, (first, second, replacement)),
            destination,
        )
        self.assertEqual(list(destination), ["first", "second"])
        self.assertIs(destination["first"], replacement)
        final = Field("second")
        self.assertIs(_dataclasses_rs.set_field(destination, final), destination)
        self.assertEqual(list(destination), ["first", "second"])
        self.assertIs(destination["second"], final)

    def test_iterator_exception_keeps_prior_insertions_and_releases_iterator(self):
        error = RuntimeError("iteration stopped")
        first = Field("first")
        iterator_refs = []

        class Iterator:
            def __init__(self):
                self.pending = True

            def __iter__(self):
                return self

            def __next__(self):
                if self.pending:
                    self.pending = False
                    return first
                raise error

        class Values:
            def __iter__(self):
                iterator = Iterator()
                iterator_refs.append(weakref.ref(iterator))
                return iterator

        destination = {}
        try:
            _dataclasses_rs.merge_fields(destination, Values())
        except RuntimeError as caught:
            self.assertIs(caught, error)
        else:
            self.fail("iterator exception was lost")
        self.assertEqual(destination, {"first": first})
        error.__traceback__ = None
        self.assertIsNone(iterator_refs[0]())

    def test_name_lookup_exception_is_preserved_by_both_helpers(self):
        error = LookupError("field name unavailable")

        class BrokenField:
            @property
            def name(self):
                raise error

        for helper, value in (
            (_dataclasses_rs.set_field, BrokenField()),
            (_dataclasses_rs.merge_fields, [BrokenField()]),
        ):
            destination = {}
            try:
                helper(destination, value)
            except LookupError as caught:
                self.assertIs(caught, error)
            else:
                self.fail("field lookup exception was lost")
            self.assertEqual(destination, {})

    def test_hash_exception_keeps_prior_insertions(self):
        error = ValueError("field name hash failed")

        class Name:
            def __hash__(self):
                raise error

        first = Field("first")
        destination = {}
        try:
            _dataclasses_rs.merge_fields(destination, [first, Field(Name())])
        except ValueError as caught:
            self.assertIs(caught, error)
        else:
            self.fail("hash exception was lost")
        self.assertEqual(destination, {"first": first})

    def test_arity_errors_and_keyword_rejection(self):
        for name in ("merge_fields", "set_field"):
            helper = getattr(_dataclasses_rs, name)
            for args in ((), ({},), ({}, [], None)):
                with self.assertRaises(TypeError) as caught:
                    helper(*args)
                self.assertEqual(str(caught.exception), f"{name}() takes exactly 2 arguments")
            with self.assertRaises(TypeError):
                helper(destination={}, field=Field("name"))


if __name__ == "__main__":
    unittest.main()
