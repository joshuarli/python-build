import json
import subprocess
import sys


PROBE = r'''
import hashlib
import hmac
import json
import _hashlib
import array

names = [
    'sha1', 'SHA1', 'SHA-1', 'sha-1', 'sha224', 'SHA-224', 'sha-224',
    'sha256', 'SHA-256', 'sha-256', 'sha384', 'SHA-384', 'sha-384',
    'sha512', 'SHA-512', 'sha-512', 'sha512_224', 'SHA512-224',
    'sha512-224', 'sha-512-224', 'sha512_256', 'SHA512-256',
    'sha512-256', 'sha3_256', 'SHA3-256', 'sha3-256', 'shake_128',
    'SHAKE-128', 'shake-128', 'ripemd160', 'RIPEMD160', 'ripemd-160',
    'sm3', 'SM3', 'md5-sha1', 'MD5-SHA1', 'md5_sha1', 'sha_256',
    'not-a-digest',
]

def capture(function):
    try:
        return ['ok', function()]
    except Exception as error:
        return [type(error).__name__, str(error)]

available = sorted(hashlib.algorithms_available)
probe = {
    'available': available,
    'names': {},
    'native_names': {},
    'hmac': {},
    'pbkdf2': {},
    'buffer_updates': {},
}

for name in names:
    def describe_hash(name=name):
        value = hashlib.new(name, b'abc')
        return [value.name, value.digest_size, value.block_size, value.hexdigest()]
    def describe_native_hash(name=name):
        value = _hashlib.new(name, b'abc')
        return [value.name, value.digest_size, value.block_size, value.hexdigest()]
    probe['names'][name] = capture(describe_hash)
    probe['native_names'][name] = capture(describe_native_hash)

key = bytes(range(100))
message = b'abc'
for name in available:
    def describe_hmac(name=name):
        value = hmac.new(key, message, name)
        copy = value.copy()
        value.update(memoryview(bytearray(b'!')))
        return [
            hmac.digest(key, message, name).hex(),
            copy.hexdigest(),
            value.hexdigest(),
            value.name,
            value.digest_size,
            value.block_size,
        ]
    def derive(name=name):
        return hashlib.pbkdf2_hmac(name, key, b'salt', 3, 57).hex()
    probe['hmac'][name] = capture(describe_hmac)
    probe['pbkdf2'][name] = capture(derive)

for name, make in (
    ('hash', lambda: hashlib.sha256()),
    ('hmac', lambda: hmac.new(b'key', digestmod='sha256')),
):
    for input_name, value in (
        ('typed', array.array('I', [1, 2, 3])),
        ('strided', memoryview(b'abcdef')[::2]),
    ):
        def update_buffer(make=make, value=value):
            result = make()
            result.update(value)
            return result.hexdigest()
        probe['buffer_updates'][f'{name}_{input_name}'] = capture(update_buffer)

probe['scrypt_boundary'] = capture(
    lambda: hashlib.scrypt(b'p', salt=b's', n=16, r=1, p=1, maxmem=2432).hex()
)
probe['scrypt_parameter_bounds'] = {}
for parameter in ('n', 'r', 'p'):
    for label, value in (
        ('signed_max', 2**63),
        ('unsigned_max', 2**64 - 1),
        ('unsigned_overflow', 2**64),
        ('negative', -1),
    ):
        def check_scrypt_bounds(parameter=parameter, value=value):
            parameters = {'n': 16, 'r': 1, 'p': 1}
            parameters[parameter] = value
            return hashlib.scrypt(
                b'p', salt=b's', maxmem=1024, dklen=16, **parameters
            ).hex()
        probe['scrypt_parameter_bounds'][f'{parameter}_{label}'] = capture(
            check_scrypt_bounds
        )
class Indexable:
    def __init__(self, value):
        self.value = value

    def __index__(self):
        return self.value

probe['scrypt_index_parameters'] = capture(
    lambda: hashlib.scrypt(
        b'p',
        salt=b's',
        n=Indexable(16),
        r=Indexable(1),
        p=Indexable(1),
        maxmem=2432,
        dklen=16,
    ).hex()
)
print(json.dumps(probe, sort_keys=True))
'''


def run(python):
    result = subprocess.run(
        [python, '-c', PROBE],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise SystemExit(result.stderr)
    return json.loads(result.stdout)


if len(sys.argv) != 3:
    raise SystemExit('usage: compare-reference.py <reference-python> <candidate-python>')

reference = run(sys.argv[1])
candidate = run(sys.argv[2])
if reference != candidate:
    for section, expected in reference.items():
        actual = candidate.get(section)
        if expected == actual:
            continue
        print(f'difference in {section}:')
        if isinstance(expected, dict) and isinstance(actual, dict):
            for name, expected_value in expected.items():
                actual_value = actual.get(name)
                if expected_value != actual_value:
                    print(f'  {name}: reference={expected_value!r} candidate={actual_value!r}')
        else:
            print(f'  reference={expected!r} candidate={actual!r}')
    raise SystemExit(1)

print(
    f"matched {len(reference['names'])} name and error cases, "
    f"{len(reference['hmac'])} HMAC/PBKDF2 algorithms, and the scrypt boundary"
    f" ({len(reference['buffer_updates'])} buffer cases, "
    f"{len(reference['scrypt_parameter_bounds'])} scrypt parameter bounds, "
    "and scrypt __index__ conversion)"
)
