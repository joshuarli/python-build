import gc
import socket
import sys
from concurrent import interpreters
from concurrent.futures import InterpreterPoolExecutor, ThreadPoolExecutor
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

TLS_EXPECTED = ("TLSv1.2", "rejected", "TLSv1.3", "rejected")
UNEXPECTED_MAIN_IMPORTS = {"ssl", "_ssl", "_hashlib", "_hashlib_graviola"}.intersection(sys.modules)
if UNEXPECTED_MAIN_IMPORTS:
    raise AssertionError(("combined extensions imported in the main interpreter", UNEXPECTED_MAIN_IMPORTS))


def worker(label, port, tls_source, certdata):
    import _ssl
    import ssl

    from subinterpreter_worker import calculate

    if not _ssl.__file__.endswith(".py"):
        raise AssertionError(("_ssl is not the Python RTLS marker", _ssl.__file__))

    calculate(label, port)

    tls_worker_path = Path(tls_source) / "subinterpreter_worker.py"
    spec = spec_from_file_location("combined_rtls_worker", tls_worker_path)
    if spec is None or spec.loader is None:
        raise AssertionError(("TLS worker cannot be loaded", tls_worker_path))
    tls_worker = module_from_spec(spec)
    spec.loader.exec_module(tls_worker)
    result = tls_worker.run(certdata)
    if result != TLS_EXPECTED:
        raise AssertionError((result, TLS_EXPECTED))
    if ssl.TLSVersion.TLSv1_3.name != "TLSv1_3":
        raise AssertionError("TLS enum metadata changed")
    return result


def expression(label, port, tls_source, certdata):
    driver_directory = Path(__file__).parent.resolve()
    call = (
        f"(__import__('sys').path.insert(0, {str(driver_directory)!r}), "
        f"__import__('combined_tls').worker({label!r}, {port!r}, "
        f"{str(tls_source)!r}, {str(certdata)!r}))[1]"
    )
    return call


def run_pair(submit, tls_source, certdata):
    with socket.socket() as listener:
        listener.settimeout(30)
        listener.bind(("127.0.0.1", 0))
        listener.listen(2)
        port = listener.getsockname()[1]
        futures = [
            submit(label, port, tls_source, certdata)
            for label in ("worker-0", "worker-1")
        ]
        connections = []
        try:
            labels = set()
            for _ in range(2):
                connection, _address = listener.accept()
                connection.settimeout(30)
                connections.append(connection)
                labels.add("worker-" + connection.recv(1).decode())
            if labels != {"worker-0", "worker-1"}:
                raise AssertionError(labels)
            for connection in connections:
                connection.sendall(b"g")
            return [future.result(timeout=120) for future in futures]
        finally:
            for connection in connections:
                connection.close()


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: combined_tls.py <tls-source> <certdata>")
    tls_source = Path(sys.argv[1]).resolve()
    certdata = Path(sys.argv[2]).resolve()

    for _iteration in range(3):
        workers = [interpreters.create(), interpreters.create()]
        try:
            with ThreadPoolExecutor(max_workers=2) as threads:
                results = run_pair(
                    lambda label, port, source, data, workers=workers: threads.submit(
                        execute,
                        workers[0 if label == "worker-0" else 1],
                        label,
                        port,
                        source,
                        data,
                    ),
                    tls_source,
                    certdata,
                )
            if results != [None, None]:
                raise AssertionError(results)
        finally:
            for worker_interpreter in workers:
                worker_interpreter.close()
        gc.collect()

    with InterpreterPoolExecutor(max_workers=2) as executor:
        results = run_pair(
            lambda label, port, source, data: executor.submit(
                eval,
                expression(label, port, source, data),
            ),
            tls_source,
            certdata,
        )
    if results != [TLS_EXPECTED, TLS_EXPECTED]:
        raise AssertionError(results)
    print("combined TLS/hash workers passed three create/destroy cycles and concurrent executor startup")


def execute(worker_interpreter, label, port, tls_source, certdata):
    code = (
        "import sys\n"
        f"sys.path.insert(0, {str(Path(__file__).parent.resolve())!r})\n"
        f"import combined_tls\n"
        f"assert combined_tls.worker({label!r}, {port!r}, {str(tls_source)!r}, "
        f"{str(certdata)!r}) == {TLS_EXPECTED!r}"
    )
    return worker_interpreter.exec(code)


if __name__ == "__main__":
    main()
