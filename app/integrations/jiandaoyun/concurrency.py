"""Shared JianDaoYun request pressure controls."""

from __future__ import annotations

import threading
from typing import Callable, TypeVar

from app.concurrency import RateLimitedExecutor, SingleFlight


T = TypeVar("T")
_LOCK = threading.Lock()
_EXECUTORS: dict[tuple[str, int, float], RateLimitedExecutor] = {}
_SINGLEFLIGHT = SingleFlight()


def run_query(
    *, connection_key: str, query_key: str, max_concurrency: int,
    requests_per_second: float, singleflight: bool, operation: Callable[[], T],
) -> T:
    executor_key = (connection_key, max_concurrency, requests_per_second)
    with _LOCK:
        executor = _EXECUTORS.setdefault(
            executor_key, RateLimitedExecutor(max_concurrency, requests_per_second)
        )

    def execute() -> T:
        return executor.run(operation)

    return _SINGLEFLIGHT.run(query_key, execute) if singleflight else execute()
