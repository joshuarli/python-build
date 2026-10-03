"""Exercise registered native pointers through a pinned-header C observer."""
import importlib.util
import sys
import _hmac_rs as native
spec = importlib.util.spec_from_file_location('_hmac_rs_abi_test', sys.argv.pop(1))
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)
observer.module_contract(native)
state = observer.drive(native, 'new', (b'key', 'sha256'))
assert observer.drive(native, 'update', (state, b'message')) is state
copied = observer.drive(native, 'copy', (state,))
expected = native.compute_digest(b'key', b'message', 'sha256')
assert observer.drive(native, 'digest', (copied,)) == expected
assert observer.drive(native, 'hexdigest', (copied,)) == expected.hex()
assert observer.drive(native, 'compute_digest', (b'key', b'message', 'sha256')) == expected
print('OK _hmac_rs pinned-header live native ABI')
