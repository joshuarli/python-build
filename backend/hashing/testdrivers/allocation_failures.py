import _hashlib_graviola
import _testcapi
import sys


def check(factory, arguments, expected):
    failed_allocations = []
    for allocation in range(32):
        held = [tuple([None, None, None]) for _ in range(4096)]
        sys._clear_internal_caches()
        try:
            result = _testcapi.call_with_nomemory(
                allocation,
                0,
                factory,
                *arguments,
            )
        except MemoryError:
            failed_allocations.append(allocation)
        else:
            if _hashlib_graviola.state_digest(result[0]).hex() != expected:
                raise AssertionError((allocation, result))
            del result
        del held

        recovered = factory(*arguments)
        if _hashlib_graviola.state_digest(recovered[0]).hex() != expected:
            raise AssertionError((allocation, recovered))
        del recovered
    if not failed_allocations:
        raise AssertionError((factory.__name__, "no allocation failure observed"))
    return failed_allocations


hash_failures = check(
    _hashlib_graviola.hash_state_new,
    ("sha512_224", b"allocator"),
    "20f3261798ec64ef8c984e2fce39395c5fcbcbbe6cb7923f7df56f61",
)
hmac_failures = check(
    _hashlib_graviola.hmac_state_new,
    (b"key", "sha256"),
    "5d5d139563c95b5967b9bd9a8c9b233a9dedb45072794cd232dc1b74832607d0",
)
print(f"hash constructor recovered after allocation failures at {hash_failures}")
print(f"HMAC constructor recovered after allocation failures at {hmac_failures}")
