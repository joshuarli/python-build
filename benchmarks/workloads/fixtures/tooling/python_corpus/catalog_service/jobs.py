"""Bounded background job scheduling for batch catalog operations."""

from __future__ import annotations

import concurrent.futures
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Generic, TypeVar


Result = TypeVar("Result")


class JobState(str, Enum):
    """Lifecycle states exposed to job status callers."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class Job(Generic[Result]):
    """Mutable state associated with one submitted operation."""

    identifier: str
    function: Callable[[], Result]
    state: JobState = JobState.QUEUED
    created_at: float = field(default_factory=time.monotonic)
    started_at: float | None = None
    finished_at: float | None = None
    result: Result | None = None
    error: BaseException | None = None
    future: concurrent.futures.Future[Result] | None = None


class JobQueue:
    """Track futures and expose explicit state transitions."""

    def __init__(self, workers: int = 2) -> None:
        if workers < 1:
            raise ValueError("workers must be positive")
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
        self._jobs: dict[str, Job[object]] = {}
        self._lock = threading.RLock()

    def submit(self, identifier: str, function: Callable[[], Result]) -> Job[Result]:
        """Submit a callable unless its stable identifier is already active."""
        with self._lock:
            if identifier in self._jobs:
                raise ValueError(f"job identifier already exists: {identifier}")
            job: Job[Result] = Job(identifier, function)
            self._jobs[identifier] = job
            job.future = self._executor.submit(self._execute, job)
            return job

    def _execute(self, job: Job[Result]) -> Result:
        with self._lock:
            if job.state is JobState.CANCELLED:
                raise concurrent.futures.CancelledError()
            job.state = JobState.RUNNING
            job.started_at = time.monotonic()
        try:
            result = job.function()
        except BaseException as error:
            with self._lock:
                job.error = error
                job.state = JobState.FAILED
                job.finished_at = time.monotonic()
            raise
        with self._lock:
            job.result = result
            job.state = JobState.SUCCEEDED
            job.finished_at = time.monotonic()
        return result

    def cancel(self, identifier: str) -> bool:
        """Cancel a queued operation and publish its terminal state."""
        with self._lock:
            job = self._jobs[identifier]
            future = job.future
            if future is None or not future.cancel():
                return False
            job.state = JobState.CANCELLED
            job.finished_at = time.monotonic()
            return True

    def status(self, identifier: str) -> Job[object]:
        """Return a job record after resolving the submitted future."""
        with self._lock:
            return self._jobs[identifier]

    def close(self, *, wait: bool = True) -> None:
        """Stop accepting work and finish or cancel all pending futures."""
        self._executor.shutdown(wait=wait, cancel_futures=not wait)
