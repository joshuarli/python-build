"""Check the exact-header fast path and the unchanged fallback boundary."""

import json
import tarfile

import _tar_checksum_proof


def result(function, value):
    try:
        return ("value", function(value))
    except Exception as exc:
        return ("error", type(exc).__name__, str(exc))


def main():
    original = tarfile.calc_chksums

    def candidate(buf):
        if type(buf) is bytes and len(buf) == 512:
            return _tar_checksum_proof.scan(buf)
        return original(buf)

    high = bytearray(512)
    high[0] = 255
    high[147] = 128
    high[148:156] = b"\xff" * 8
    high[156] = 127
    high[511] = 254

    class BytesSubclass(bytes):
        pass

    cases = {
        "zero": bytes(512),
        "all_ff": bytes([255]) * 512,
        "mixed_high": bytes(high),
        "ignored_field": bytes([255]) * 148 + b"changes!" + bytes(356),
        "short": bytes(511),
        "long": bytes(513),
        "bytearray": bytearray(512),
        "memoryview": memoryview(bytes(512)),
        "subclass": BytesSubclass(512),
    }
    observations = {}
    for name, value in cases.items():
        before = result(original, value)
        after = result(candidate, value)
        if before != after:
            raise AssertionError((name, before, after))
        observations[name] = {"kind": before[0], "value": before[1:]}
    for value in (bytes(511), bytearray(512), memoryview(bytes(512))):
        if result(_tar_checksum_proof.scan, value)[0] != "error":
            raise AssertionError("extension accepted a non-exact header")
    print(json.dumps({"extension": _tar_checksum_proof.__file__,
                      "cases": observations}, sort_keys=True))


if __name__ == "__main__":
    main()
