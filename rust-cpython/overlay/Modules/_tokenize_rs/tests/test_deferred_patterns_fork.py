"""Bounded fork correctness fixture requiring a process-capable test runner."""
import importlib
import os
import select
import signal
import sys
import threading
import time
import tokenize
import _tokenize_patterns

# Reload exercises the registered callback's lookup of the replacement lock.
importlib.reload(tokenize)
started = threading.Event()
release = threading.Event()
original_build = _tokenize_patterns._build_patterns
errors = []
cleanup_errors = []

def blocked_build(operators):
    started.set()
    if not release.wait(20):
        raise AssertionError('parent did not release grammar construction')
    return original_build(operators)

def initialize():
    try:
        tokenize.Token
    except BaseException as error:
        errors.append(error)

def reap(pid):
    deadline = time.monotonic() + 10
    while True:
        waited, status = os.waitpid(pid, os.WNOHANG)
        if waited == pid:
            return status
        if time.monotonic() >= deadline:
            raise AssertionError('owned fork child did not terminate')
        time.sleep(0.01)

def cleanup(label, action):
    try:
        action()
    except BaseException as error:
        cleanup_errors.append(f'{label}: {error!r}')

worker = threading.Thread(target=initialize)
worker_started = False
read_fd = write_fd = None
ready_read_fd = ready_write_fd = None
child = None
try:
    _tokenize_patterns._build_patterns = blocked_build
    read_fd, write_fd = os.pipe()
    ready_read_fd, ready_write_fd = os.pipe()
    worker.start()
    worker_started = True
    assert started.wait(10), 'grammar initialization did not enter its factory'
    child = os.fork()
    if child == 0:
        exit_code = 1
        try:
            os.close(read_fd)
            os.close(ready_write_fd)
            assert select.select([ready_read_fd], [], [], 10)[0], 'parent did not acknowledge child ownership'
            assert os.read(ready_read_fd, 1) == b'1', 'parent ownership acknowledgement failed'
            os.close(ready_read_fd)
            _tokenize_patterns._build_patterns = original_build
            assert isinstance(tokenize.Token, str)
            assert isinstance(tokenize.endpats, dict)
            os.write(write_fd, b'1')
            exit_code = 0
        finally:
            os._exit(exit_code)
    os.close(ready_read_fd)
    ready_read_fd = None
    # The fork wrapper observes the child's owned group before returning.
    os.write(ready_write_fd, b'1')
    os.close(ready_write_fd)
    ready_write_fd = None
    os.close(write_fd)
    write_fd = None
    assert select.select([read_fd], [], [], 10)[0], 'child grammar reader blocked'
    assert os.read(read_fd, 1) == b'1', 'child grammar reader failed'
    status = reap(child)
    child = None
    assert os.waitstatus_to_exitcode(status) == 0, status
finally:
    primary_error = sys.exc_info()[1]
    cleanup('restore factory', lambda: setattr(_tokenize_patterns, '_build_patterns', original_build))
    cleanup('release parent factory', release.set)
    if child is not None:
        def kill_child():
            try:
                os.kill(child, signal.SIGKILL)
            except ProcessLookupError:
                pass
        cleanup('kill owned child', kill_child)
        cleanup('reap owned child', lambda: reap(child))
    if read_fd is not None:
        cleanup('close read pipe', lambda: os.close(read_fd))
    if write_fd is not None:
        cleanup('close write pipe', lambda: os.close(write_fd))
    if ready_read_fd is not None:
        cleanup('close readiness read pipe', lambda: os.close(ready_read_fd))
    if ready_write_fd is not None:
        cleanup('close readiness write pipe', lambda: os.close(ready_write_fd))
    if worker_started:
        cleanup('join parent initializer', lambda: worker.join(10))
        if worker.is_alive():
            cleanup_errors.append('parent initializer remains alive')
    if cleanup_errors:
        if primary_error is not None:
            for error in cleanup_errors:
                primary_error.add_note(error)
        else:
            raise AssertionError('; '.join(cleanup_errors))
assert not errors, errors
print('fork child resolves grammar after reload while parent initialization owner vanishes')
