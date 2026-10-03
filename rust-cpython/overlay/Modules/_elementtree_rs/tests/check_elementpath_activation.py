"""ElementPath activates on selector demand and keeps one shared provider."""
import importlib
import sys
import types
import xml.etree.ElementTree as ET
import _elementtree

NAME = 'xml.etree.ElementPath'
assert NAME not in sys.modules
assert ET.Element is _elementtree.Element
root = ET.fromstring('<root><item kind="x">first</item><item kind="y">second</item></root>')
assert ET.tostring(root, encoding='unicode') == '<root><item kind="x">first</item><item kind="y">second</item></root>'
assert root.find('item') is root[0]
assert root.findtext('item') == 'first'
assert root.findall('item') == list(root)
assert NAME not in sys.modules

# The first unsupported simple-path spelling imports the shared selector provider.
class BlockElementPath:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == NAME:
            raise ImportError('selector import blocked')
blocker = BlockElementPath()
sys.meta_path.insert(0, blocker)
try:
    try:
        root.find('./item')
    except ImportError as error:
        assert str(error) == 'selector import blocked'
    else:
        raise AssertionError('selector import failure did not propagate')
    assert NAME not in sys.modules
    assert root.find('item') is root[0]
finally:
    sys.meta_path.remove(blocker)
# A successful nested selector call may publish the same module during import.
import importlib.machinery
nested = []
late_failure = ImportError('selector loader stopped')
class ReentrantFinder:
    fail_once = True
    def find_spec(self, fullname, path=None, target=None):
        if fullname != NAME:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        original_loader = spec.loader
        class Loader:
            def create_module(self, spec):
                return original_loader.create_module(spec)
            def exec_module(self, module):
                module.__loader__ = original_loader
                spec.loader = original_loader
                try:
                    root.find('./item')
                except AttributeError:
                    pass
                else:
                    raise AssertionError('partial selector module unexpectedly had find')
                original_loader.exec_module(module)
                nested.append(root.find("./item[@kind='x']"))
                if finder.fail_once:
                    finder.fail_once = False
                    raise late_failure
        spec.loader = Loader()
        return spec
finder = ReentrantFinder()
sys.meta_path.insert(0, finder)
try:
    try:
        root.find("./item[@kind='x']")
    except ImportError as error:
        assert error is late_failure
    else:
        raise AssertionError('late selector import failure was swallowed')
    assert NAME not in sys.modules
    assert root.find("./item[@kind='x']") is root[0]
    assert nested == [root[0], root[0]]
finally:
    sys.meta_path.remove(finder)
provider = sys.modules[NAME]
assert ET.ElementPath is provider
assert root.findtext('./item') == 'first'
assert root.findall('./item') == list(root)
assert list(root.iterfind('./item')) == list(root)

# Native methods resolve the current provider attributes and retain its module.
original = {name: getattr(provider, name) for name in ('find', 'findtext', 'findall', 'iterfind')}
calls = []
def observed(name):
    def call(*args):
        calls.append(name)
        return original[name](*args)
    return call
try:
    for name in original:
        setattr(provider, name, observed(name))
    assert root.find('./item') is root[0]
    assert root.findtext('./item') == 'first'
    assert root.findall('./item') == list(root)
    assert list(root.iterfind('./item')) == list(root)
    assert calls == ['find', 'iterfind', 'findtext', 'iterfind', 'findall', 'iterfind', 'iterfind']
    held = root.iterfind('./item')
    sys.modules[NAME] = types.ModuleType(NAME)
    assert list(held) == list(root)
    assert root.find('./item') is root[0]
finally:
    sys.modules[NAME] = provider
    for name, function in original.items():
        setattr(provider, name, function)

# Python elements and subclasses use the same selector module and shared cache.
python = ET._Element_Py('root')
child = ET._Element_Py('item', {'kind': 'x'})
child.text = 'python'
python.append(child)
assert python.find("./item[@kind='x']") is child
assert python.findtext('./item') == 'python'
assert python.findall('./item') == [child]
assert list(python.iterfind('./item')) == [child]
class DerivedElement(ET.Element):
    pass
custom = DerivedElement('root')
custom.append(ET.Element('item'))
assert list(custom.iterfind('./item')) == [custom[0]]
original_prepare = provider.ops['']
prepared = []
def prepare(next_token, token):
    prepared.append(token[1])
    return original_prepare(next_token, token)
provider._cache.clear()
provider.ops[''] = prepare
try:
    assert root.find('./item') is root[0]
    assert prepared == ['item']
finally:
    provider.ops[''] = original_prepare
    provider._cache.clear()

held_find = root.find
importlib.reload(ET)
assert ET.Element is _elementtree.Element
assert ET.ElementPath is provider
assert held_find('./item') is root[0]
print('cold activation, import retry, four delegates, held provider, selectors, C/Python types and reload passed')
