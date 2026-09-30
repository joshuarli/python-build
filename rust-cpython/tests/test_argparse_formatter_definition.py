"""Observable behavior of argparse's built-in formatter definition guard."""

import subprocess
import sys
import unittest
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "overlay" / "Lib" / "argparse.py"


@unittest.skipUnless(sys.version_info >= (3, 16), "requires the staged Python 3.16 syntax")
class ArgparseFormatterDefinitionTests(unittest.TestCase):
    def run_isolated(self, body):
        loader = (
            "import sys, types\n"
            "argparse = types.ModuleType('argparse')\n"
            "sys.modules['argparse'] = argparse\n"
            f"argparse.__file__ = {str(SOURCE)!r}\n"
            "with open(argparse.__file__) as source:\n"
            "    exec(compile(source.read(), argparse.__file__, 'exec'), argparse.__dict__)\n"
        )
        result = subprocess.run(
            [sys.executable, "-I", "-S", "-c", loader + body],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_modified_docstring_does_not_execute_value_equality(self):
        self.run_isolated("""
class Docstring(str):
    def __eq__(self, other):
        raise AssertionError('formatter definition value equality executed')
argparse.HelpFormatter.__doc__ = Docstring(argparse.HelpFormatter.__doc__)
parser = argparse.ArgumentParser(color=False)
assert parser.parse_args([]).__dict__ == {}
""")

    def test_modified_constructor_retains_terminal_width(self):
        self.run_isolated("""
import os
os.environ['COLUMNS'] = '117'
original = argparse.HelpFormatter.__init__
widths = []
def custom_init(self, *args, **kwargs):
    assert 'width' not in kwargs
    original(self, *args, **kwargs)
    widths.append(self._width)
argparse.HelpFormatter.__init__ = custom_init
argparse.ArgumentParser(color=False)
assert widths == [115], widths
""")

    def test_unchanged_builtin_validation_does_not_import_shutil(self):
        self.run_isolated("""
assert 'shutil' not in sys.modules
parser = argparse.ArgumentParser(color=False)
parser.add_argument('--value')
assert parser.parse_args(['--value', 'example']).value == 'example'
assert 'shutil' not in sys.modules
""")

    def test_replaced_definition_key_with_none_retains_terminal_width(self):
        self.run_isolated("""
import os
os.environ['COLUMNS'] = '117'
del argparse.HelpFormatter._indent
argparse.HelpFormatter.replacement_attribute = None
parser = argparse.ArgumentParser(color=False)
assert parser._cached_formatter._width == 115
""")


if __name__ == "__main__":
    unittest.main()
