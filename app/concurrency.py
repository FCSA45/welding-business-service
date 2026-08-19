"""Small in-process concurrency primitives; no Redis or message queue required."""

from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import Future
from typing import Callable, TypeVar


T = TypeVar("T")


def run_async_blocking(factory: Callable[[], T]) -> T:
    """Run an async factory from sync code, including inside an active loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())

    result: list[T] = []
    error: list[BaseException] = []

    def runner() -> None:
        try:
            result.append(asyncio.run(factory()))
        except BaseException as exc:
            error.append(exc)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if error:
        raise error[0]
    return result[0]


class RateLimitedExecutor:
    def __init__(self, max_concurrency: int, requests_per_second: float) -> None:
        self._semaphore = threading.BoundedSemaphore(max_concurrency)
        self._interval = 1.0 / requests_per_second
        self._rate_lock = threading.Lock()
        self._next_start = 0.0

    def run(self, operation: Callable[[], T]) -> T:
        with self._semaphore:
            with self._rate_lock:
                now = time.monotonic()
                delay = max(0.0, self._next_start - now)
                self._next_start = max(now, self._next_start) + self._interval
            if delay:
                time.sleep(delay)
            return operation()


class SingleFlight:
    """Concurrent calls for the same key share one result or exception."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._flights: dict[str, Future] = {}

    def run(self, key: str, operation: Callable[[], T]) -> T:
        with self._lock:
            future = self._flights.get(key)
            leader = future is None
            if leader:
                future = Future()
                self._flights[key] = future
        if not leader:
            return future.result()
        try:
            result = operation()
        except BaseException as exc:
            future.set_exception(exc)
            raise
        else:
            future.set_result(result)
            return result
        finally:
            with self._lock:
                self._flights.pop(key, None)


class KeyedMutex:
    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[str, tuple[threading.Lock, int]] = {}

    def run(self, key: str, operation: Callable[[], T]) -> T:
        with self._guard:
            lock, users = self._locks.get(key, (threading.Lock(), 0))
            self._locks[key] = (lock, users + 1)
        try:
            with lock:
                return operation()
        finally:
            with self._guard:
                current_lock, users = self._locks[key]
                if users <= 1:
                    self._locks.pop(key, None)
                else:
                    self._locks[key] = (current_lock, users - 1)


class SemaphorePool:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[tuple[str, int], threading.BoundedSemaphore] = {}

    def get(self, name: str, limit: int) -> threading.BoundedSemaphore:
        with self._lock:
            return self._items.setdefault((name, limit), threading.BoundedSemaphore(limit))


semaphore_pool = SemaphorePool()
