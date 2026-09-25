"""Check exact public Base64 output from an installed CPython variant."""

import base64
import binascii
import hashlib
import json
import sys
from pathlib import Path


TABLE = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"


def reference(data: bytes) -> bytes:
    output = bytearray()
    for start in range(0, len(data), 3):
        group = data[start:start + 3]
        value = int.from_bytes(group, "big") << (8 * (3 - len(group)))
        output.append(TABLE[(value >> 18) & 63])
        output.append(TABLE[(value >> 12) & 63])
        output.append(TABLE[(value >> 6) & 63] if len(group) > 1 else ord("="))
        output.append(TABLE[value & 63] if len(group) > 2 else ord("="))
    return bytes(output)


def main() -> None:
    module = Path(binascii.__file__).resolve()
    stage = Path(sys.prefix).resolve()
    if not module.is_relative_to(stage):
        raise SystemExit(f"binascii was loaded outside the installed tree: {module}")
    lengths = (0, 1, 2, 3, 47, 48, 49, 4094, 4095, 4096, 4097, 4098,
               65535, 65536, 65537, 1048576, 1048577, 1048578)
    digest = hashlib.sha256()
    for length in lengths:
        value = bytes((index * 131 + 17) & 255 for index in range(length))
        expected = reference(value)
        for data in (value, bytearray(value), memoryview(value)):
            if base64.b64encode(data) != expected:
                raise SystemExit(f"public Base64 output differs at {length} bytes")
            if binascii.b2a_base64(data, newline=False) != expected:
                raise SystemExit(f"binascii Base64 output differs at {length} bytes")
        if binascii.b2a_base64(value) != expected + b"\n":
            raise SystemExit(f"newline output differs at {length} bytes")
        if binascii.b2a_base64(value, padded=False, newline=False) != expected.rstrip(b"="):
            raise SystemExit(f"unpadded output differs at {length} bytes")
        if base64.b64encode(value, altchars=b"-_") != expected.translate(bytes.maketrans(b"+/", b"-_")):
            raise SystemExit(f"alternate alphabet output differs at {length} bytes")
        digest.update(len(expected).to_bytes(8, "little"))
        digest.update(expected)
    print(json.dumps({
        "python": sys.version.split()[0],
        "binascii_path": str(module),
        "binascii_sha256": hashlib.sha256(module.read_bytes()).hexdigest(),
        "vectors": len(lengths),
        "public_output_sha256": digest.hexdigest(),
        "result": "pass",
    }, sort_keys=True))


if __name__ == "__main__":
    main()
