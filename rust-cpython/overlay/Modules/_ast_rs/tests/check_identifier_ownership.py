"""Observable parser identifier contracts with live normalization callbacks."""
import ast
import gc
import sys
import unicodedata
import unittest
import weakref
from unittest.mock import patch


class IdentifierContracts(unittest.TestCase):
    def test_ascii_names_compile_and_execute_without_normalization(self):
        source = 'value = 4\nclass Example:\n    pass\ndef calculate(argument):\n    return argument + value\nresult = calculate(3)\n'
        def forbidden(*args):
            raise AssertionError('ASCII identifier unexpectedly normalized')
        with patch.object(unicodedata, 'normalize', forbidden):
            code = compile(source, '<ascii identifiers>', 'exec')
        namespace = {}
        exec(code, namespace)
        self.assertEqual(namespace['result'], 7)
        self.assertEqual(namespace['Example'].__name__, 'Example')
        self.assertEqual(namespace['calculate'].__name__, 'calculate')

    def test_normalization_order_and_parser_callback_capture(self):
        original = unicodedata.normalize
        calls = []
        later = []
        def replacement(form, text):
            later.append((form, text))
            return original(form, text)
        def normalize(form, text):
            calls.append((form, text))
            unicodedata.normalize = replacement
            return original(form, text)
        source = '\u212a = 3\n\u00e9 = 4\n'
        with patch.object(unicodedata, 'normalize', normalize):
            code = compile(source, '<normalized identifiers>', 'exec')
            self.assertEqual(calls, [('NFKC', '\u212a'), ('NFKC', '\u00e9')])
            self.assertEqual(later, [])
            compile('\u00f1 = 5', '<next parser>', 'exec')
            self.assertEqual(later, [('NFKC', '\u00f1')])
        namespace = {}
        exec(code, namespace)
        self.assertEqual(namespace['K'], 3)
        self.assertEqual(namespace['\u00e9'], 4)
        self.assertEqual(source, '\u212a = 3\n\u00e9 = 4\n')

    def test_normalizer_string_subclass_lives_through_later_callbacks(self):
        class Name(str):
            def __str__(self):
                raise AssertionError('identifier must use Unicode data')
        references = []
        def normalize(form, text):
            self.assertEqual(form, 'NFKC')
            gc.collect()
            self.assertTrue(all(reference() is not None for reference in references))
            result = Name('owned_' + str(len(references)))
            references.append(weakref.ref(result))
            return result
        with patch.object(unicodedata, 'normalize', normalize):
            code = compile('\u00e9 = 10\n\u00f1 = 20\n', '<subclass identifiers>', 'exec')
        gc.collect()
        namespace = {}
        exec(code, namespace)
        self.assertEqual(namespace['owned_0'], 10)
        self.assertEqual(namespace['owned_1'], 20)

    def test_already_interned_normalized_name_is_valid(self):
        name = sys.intern('normalized_identifier_custom_368')
        with patch.object(unicodedata, 'normalize', lambda form, text: name):
            code = compile('\u212a = 41', '<interned normalization>', 'exec')
        namespace = {}
        exec(code, namespace)
        self.assertEqual(namespace[name], 41)

    def test_normalizer_exception_identity_and_recovery(self):
        sentinel = RuntimeError('normalization sentinel')
        def normalize(form, text):
            raise sentinel
        with patch.object(unicodedata, 'normalize', normalize):
            with self.assertRaises(RuntimeError) as caught:
                compile('\u00e9 = 1', '<normalization error>', 'exec')
            self.assertIs(caught.exception, sentinel)
        namespace = {}
        exec(compile('\u212a = 2', '<normalization recovery>', 'exec'), namespace)
        self.assertEqual(namespace['K'], 2)

    def test_invalid_normalized_result_retains_original_type_error(self):
        for result, typename in ((None, 'NoneType'), (12, 'int'), (b'name', 'bytes')):
            with self.subTest(typename=typename), patch.object(unicodedata, 'normalize', lambda *args: result):
                with self.assertRaises(TypeError) as caught:
                    compile('\u00e9 = 1', '<invalid normalization>', 'exec')
                self.assertIs(type(caught.exception), TypeError)
                self.assertEqual(str(caught.exception),
                                 'unicodedata.normalize() must return a string, not ' + typename)
        self.assertEqual(ast.parse('\u212a = 1').body[0].targets[0].id, 'K')

    def test_reentrant_compile_from_normalizer(self):
        original = unicodedata.normalize
        nested_results = []
        def normalize(form, text):
            nested = compile('nested_value = 6 * 7', '<nested compilation>', 'exec')
            namespace = {}
            exec(nested, namespace)
            nested_results.append(namespace['nested_value'])
            return original(form, text)
        source = '\u212a = 8\n'
        with patch.object(unicodedata, 'normalize', normalize):
            tree = ast.parse(source)
            code = compile(tree, '<outer compilation>', 'exec')
        self.assertEqual(nested_results, [42])
        self.assertEqual(tree.body[0].targets[0].id, 'K')
        namespace = {}
        exec(code, namespace)
        self.assertEqual(namespace['K'], 8)
        self.assertEqual(source, '\u212a = 8\n')


if __name__ == '__main__':
    unittest.main()
