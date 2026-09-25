import builtins
import collections
import importlib.util
import json
import sys
import types
from pathlib import Path

source = Path(sys.argv[1])
case = sys.argv[2]
name = '_rust_shlex_split'
events = []
original_import = builtins.__import__
original_deque = collections.deque
original_private = sys.modules.pop(name, None)
if case == 'preloaded_private':
    fake = types.ModuleType(name)
    fake.scan = lambda text: ['intercepted']
    sys.modules[name] = fake
spec = importlib.util.spec_from_file_location('shlex_guarded', source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
exec('''def baseline_split(s):
    lex = shlex(s, posix=True)
    lex.whitespace_split = True
    lex.commenters = ''
    return list(lex)
''', module.__dict__)
if case == 'StringIO':
    original = module.StringIO
    module.StringIO = lambda *args, **kwargs: (events.append('StringIO'), original(*args, **kwargs))[1]
elif case == 'list':
    module.list = lambda *args, **kwargs: (events.append('list'), list(*args, **kwargs))[1]
elif case == 'isinstance':
    module.isinstance = lambda *args, **kwargs: (events.append('isinstance'), isinstance(*args, **kwargs))[1]
elif case == 'deque':
    collections.deque = lambda *args, **kwargs: (events.append('deque'), original_deque(*args, **kwargs))[1]
elif case == 'StopIteration':
    class ReplacementStop(Exception):
        pass
    module.StopIteration = ReplacementStop
elif case == 'import_override':
    def intercept(import_name, *args, **kwargs):
        if import_name == name:
            events.append('private import')
            raise RuntimeError('intercepted private import')
        return original_import(import_name, *args, **kwargs)
    builtins.__import__ = intercept
elif case in ('__getattribute__', '__setattr__', '__new__', '__del__',
              '__len__', '__length_hint__', 'punctuation_chars'):
    cls = module.shlex
    if case == '__getattribute__':
        cls.__getattribute__ = lambda self,key: (events.append(case), object.__getattribute__(self,key))[1]
    elif case == '__setattr__':
        cls.__setattr__ = lambda self,key,value: (events.append(case), object.__setattr__(self,key,value))[1]
    elif case == '__new__':
        cls.__new__ = staticmethod(lambda cls,*args,**kwargs:(events.append(case),object.__new__(cls))[1])
    elif case == '__del__':
        cls.__del__ = lambda self: events.append(case)
    elif case == 'punctuation_chars':
        cls.punctuation_chars = property(lambda self:(events.append(case),self._punctuation_chars)[1])
    else:
        setattr(cls,case,lambda self:(events.append(case),0)[1])
elif case == 'equality_hook':
    original_read = module.shlex.read_token
    class EqualHook:
        def __get__(self, instance, owner):
            if instance is None:
                return self
            def read():
                events.append(case)
                return original_read(instance)
            return read
        def __eq__(self, other):
            return True
    module.shlex.read_token = EqualHook()
elif case == 'tampered_scan':
    module.split('echo hi')
    native = sys.modules[name]
    native.scan = lambda text: ['intercepted']
elif case == 'replaced_private':
    module.split('echo hi')
    fake = types.ModuleType(name)
    fake.scan = lambda text: ['intercepted']
    sys.modules[name] = fake
elif case not in ('ordinary', 'preloaded_private'):
    raise ValueError(case)

observations = []
for route in (module.split, module.baseline_split):
    events.clear()
    try:
        result = {'tokens': route('echo "a b" c')}
    except Exception as error:
        result = {'error_type': type(error).__name__, 'error': str(error)}
    result['events'] = len(events)
    observations.append(result)
print(json.dumps({'case': case, 'candidate': observations[0],
                  'baseline': observations[1],
                  'trusted_native_cached': module._RUST_SHLEX_SPLIT_MODULE is not None}))
builtins.__import__ = original_import
collections.deque = original_deque
if original_private is None:sys.modules.pop(name, None)
else:sys.modules[name] = original_private
