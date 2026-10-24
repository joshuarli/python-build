EXPECTED = {
    "main": (
        "21016f9a3410d7643a94c01c862471f3a67ae9d393b7cfdd34206dfd",
        "c94052fd356e1e2736aa3b7d9e0bd829adb851ab44d72e0f9e7eb86f7cef7c65",
        "14c773f09986240e866028fd126d90384622d4dfe37c5aaeae281cc5c5007a51",
        "382b2e4f99517dcc3ef0263572679d83b395b768fe28d20fe264b186385048fe",
    ),
    "worker-0": (
        "1540f51b46856806f2d625a47f30eeaed902dd9b7891907b5c979703",
        "8e390177aed919fa13b228b9ed6e2277b0278f954ce749212b9e6f4f244cd405",
        "44718077e7c5cd3195a85e8af94c783c821aae103eb0587f3d46d2e2cb49ba0c",
        "dca9e3d9a6fc208e497ffbb54a7911b28e3f9bf4c7d8e854ae9efac10e85e9bf",
    ),
    "worker-1": (
        "0995d14df88708b713116e70b5a1fa3657ade188ff4034841f77130c",
        "57974bb21ee600b4163e466b046d3ef1d6d7e7949ed6c0d0d9be30ba6e86052f",
        "aadde0a7615cd0435256d52e26996ee5325776a770ed22cef5d64d7bbc40c95d",
        "7a54186a013f1310b6642d450dd696fa5b8747d30e4e60d7b86e24581105b0ac",
    ),
}


def calculate(label, port):
    import hashlib
    import hmac
    import socket

    import _hashlib
    import _hashlib_graviola

    with socket.create_connection(("127.0.0.1", port), timeout=20) as connection:
        connection.sendall(label[-1:].encode())
        if connection.recv(1) != b"g":
            raise AssertionError("worker gate was not released")

    data = label.encode()
    digest = hashlib.new("sha512_224", data)
    digest_copy = digest.copy()
    digest.update(b"changed")
    mac = hmac.new(b"key:" + data, data, "sha3_256")
    pbkdf = hashlib.pbkdf2_hmac("sha256", data, b"salt:" + data, 17, 32)
    derived = hashlib.scrypt(
        data,
        salt=b"salt:" + data,
        n=16,
        r=1,
        p=1,
        maxmem=2432,
        dklen=32,
    )

    copied = hashlib.new("sha512_224", b"prefix").copy()
    copied_mac = hmac.new(b"key", b"prefix", "sha256").copy()
    try:
        _hashlib.new("not-a-real-hash")
    except _hashlib.UnsupportedDigestmodError:
        pass
    else:
        raise AssertionError("unsupported digest did not raise the local exception")

    result = (
        digest_copy.hexdigest(),
        mac.hexdigest(),
        pbkdf.hex(),
        derived.hex(),
    )
    if result != EXPECTED[label]:
        raise AssertionError((label, result, EXPECTED[label]))
    if copied.hexdigest() != "772807fe190a2955d3c989b1d9b2c2b408d726c60f368aa88c404d33":
        raise AssertionError("hash state copy crossed an update")
    if copied_mac.hexdigest() != "d4d6d89b3b72dabdbed156384a2a084f52b9c4aa5adfd54d13160cdf74abf150":
        raise AssertionError("HMAC state copy crossed an update")
    if _hashlib_graviola.__spec__.origin is None:
        raise AssertionError("extension origin is missing")
    return result
