"""Typed native oracle for slot export and retained-module metadata."""
import importlib
import importlib.util
import sys

import _hashlib_rs as native

spec = importlib.util.spec_from_file_location("_hashlib_slot_export_abi", sys.argv.pop(1))
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)
observer.check(native.__file__)
factory = native.new
context = factory("sha256", b"before")
copy = context.copy()
assert importlib.reload(native) is native
assert native.new is factory
assert native.HASH is type(context)
copy.update(b"after")
assert copy.digest() == factory("sha256", b"beforeafter").digest()
observer.check(native.__file__)
print("OK _hashlib_rs pinned-header immutable slot export")
