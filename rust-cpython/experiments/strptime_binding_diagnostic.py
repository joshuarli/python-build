import builtins
from datetime import datetime
import json
import sys
import types
import _strptime

FORMAT = "%Y/%m/%d %H:%M:%S"
VALUE = "2024/03/17 11:22:33"
datetime.strptime(VALUE, FORMAT)

case = sys.argv[1]
if case == "module_class":
    datetime.strptime(VALUE, FORMAT)
if case == "isinstance":
    def replacement(*args):
        raise RuntimeError("isinstance reached")
    _strptime.isinstance = replacement
elif case == "enumerate":
    def replacement(*args):
        raise RuntimeError("enumerate reached")
    _strptime.enumerate = replacement
elif case == "type":
    def replacement(*args):
        raise RuntimeError("type reached")
    _strptime.type = replacement
elif case == "len":
    def replacement(arg):
        if isinstance(arg, str):
            return 0
        return builtins.len(arg)
    _strptime.len = replacement
elif case == "import":
    original_import = builtins.__import__
    def replacement(name, *args, **kwargs):
        if name == "_rust_strptime_numeric":
            raise RuntimeError("private import reached")
        return original_import(name, *args, **kwargs)
    builtins.__import__ = replacement
elif case == "sys_modules":
    sys.modules["_rust_strptime_numeric"] = types.SimpleNamespace(
        scan=lambda value: (2000, 1, 1, 0, 0, 0)
    )
elif case == "module_class":
    module = sys.modules.get("_rust_strptime_numeric")
    if module is None:
        import _rust_strptime_numeric as module
    class Hook(types.ModuleType):
        def __getattribute__(self, name):
            if name == "scan":
                raise RuntimeError("module scan attribute reached")
            return super().__getattribute__(name)
    module.__class__ = Hook

try:
    result = datetime.strptime(VALUE, FORMAT)
    output = {"type": type(result).__name__, "value": str(result)}
except Exception as error:
    output = {"exception": type(error).__name__, "message": str(error)}
print(json.dumps({"case": case, "source": _strptime.__file__, "outcome": output}))
