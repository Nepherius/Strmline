from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from functools import lru_cache
from threading import Lock
from time import monotonic

from app.operations.defaults import TORBOX_REQUESTS_PER_MINUTE
from app.operations.metrics import OperationalMetrics, get_operational_metrics

RATE_WINDOW_SECONDS = 60.0


class TorBoxRequestCoordinator:
    """Enforce a rolling process-wide TorBox request budget."""

    def __init__(
        self,
        requests_per_minute: int,
        *,
        metrics: OperationalMetrics | None = None,
        clock: Callable[[], float] = monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if requests_per_minute <= 0:
            msg = "TorBox requests per minute must be positive."
            raise ValueError(msg)
        self.requests_per_minute = requests_per_minute
        self._metrics = metrics or get_operational_metrics()
        self._clock = clock
        self._sleep = sleep
        self._lock = Lock()
        self._admitted_calls: deque[float] = deque()
        self._metrics.configure_torbox_budget(requests_per_minute)

    def reconfigure(self, requests_per_minute: int) -> None:
        if requests_per_minute <= 0:
            msg = "TorBox requests per minute must be positive."
            raise ValueError(msg)
        with self._lock:
            self.requests_per_minute = requests_per_minute
        self._metrics.configure_torbox_budget(requests_per_minute)

    async def acquire(self) -> None:
        self._metrics.torbox_queue_entered()
        try:
            while True:
                wait_seconds = self._reserve_or_wait()
                if wait_seconds is None:
                    return
                await self._sleep(wait_seconds)
        finally:
            self._metrics.torbox_queue_left()

    def record_request_started(self) -> None:
        self._metrics.torbox_request_started()

    def record_request_finished(self, *, status_code: int | None, succeeded: bool) -> None:
        self._metrics.torbox_request_finished(
            status_code=status_code,
            succeeded=succeeded,
        )

    def _reserve_or_wait(self) -> float | None:
        with self._lock:
            now = self._clock()
            cutoff = now - RATE_WINDOW_SECONDS
            while self._admitted_calls and self._admitted_calls[0] <= cutoff:
                _ = self._admitted_calls.popleft()
            if len(self._admitted_calls) < self.requests_per_minute:
                self._admitted_calls.append(now)
                return None
            return max(0.0, self._admitted_calls[0] + RATE_WINDOW_SECONDS - now)


@lru_cache
def get_torbox_request_coordinator() -> TorBoxRequestCoordinator:
    return TorBoxRequestCoordinator(TORBOX_REQUESTS_PER_MINUTE)


def configure_torbox_request_budget(requests_per_minute: int) -> None:
    get_torbox_request_coordinator().reconfigure(requests_per_minute)


def clear_torbox_runtime() -> None:
    get_torbox_request_coordinator.cache_clear()
