import concurrent.futures
import socket
import sys
from subinterpreter_worker import EXPECTED, calculate


def main():
    if "_hashlib" in sys.modules or "_hashlib_graviola" in sys.modules:
        raise AssertionError("hash backend was imported before the concurrent first import")
    for _ in range(3):
        with socket.socket() as listener:
            listener.settimeout(20)
            listener.bind(("127.0.0.1", 0))
            listener.listen(2)
            with concurrent.futures.InterpreterPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(calculate, f"worker-{index}", listener.getsockname()[1])
                    for index in range(2)
                ]
                connections = []
                try:
                    labels = set()
                    for _ in range(2):
                        connection, _address = listener.accept()
                        connection.settimeout(20)
                        connections.append(connection)
                        labels.add("worker-" + connection.recv(1).decode())
                    if labels != {"worker-0", "worker-1"}:
                        raise AssertionError(labels)
                    for connection in connections:
                        connection.sendall(b"g")
                finally:
                    for connection in connections:
                        connection.close()
                results = [future.result(timeout=20) for future in futures]
                if results != [EXPECTED["worker-0"], EXPECTED["worker-1"]]:
                    raise AssertionError(results)
    if calculate_main() != EXPECTED["main"]:
        raise AssertionError("main interpreter digest results differ")
    print("main and two concurrent interpreter workers passed three create/destroy cycles")


def calculate_main():
    import hashlib
    import hmac

    label = "main"
    data = label.encode()
    digest = hashlib.new("sha512_224", data)
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
    return digest.hexdigest(), mac.hexdigest(), pbkdf.hex(), derived.hex()


if __name__ == "__main__":
    main()
