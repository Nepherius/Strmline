from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from time import monotonic

RECENT_CALL_WINDOW_SECONDS = 60.0
HTTP_TOO_MANY_REQUESTS = 429


@dataclass(frozen=True, slots=True)
class OperationalMetricsSnapshot:
    torbox_request_budget_per_minute: int
    torbox_requests_total: int
    torbox_requests_succeeded: int
    torbox_requests_failed: int
    torbox_responses_429: int
    torbox_calls_last_minute: int
    torbox_queue_depth: int
    resolver_cache_hits: int
    resolver_cache_misses: int
    resolver_negative_cache_hits: int
    resolver_circuit_open_rejections: int
    resolver_recovery_attempts: int
    resolver_recovery_succeeded: int
    resolver_recovery_failed: int


class OperationalMetrics:
    """Thread-safe, bounded counters that intentionally reset on process restart."""

    def __init__(self, *, clock: Callable[[], float] = monotonic) -> None:
        self._clock = clock
        self._lock = Lock()
        self._request_budget = 0
        self._requests_total = 0
        self._requests_succeeded = 0
        self._requests_failed = 0
        self._responses_429 = 0
        self._queue_depth = 0
        self._recent_calls: deque[float] = deque()
        self._resolver_cache_hits = 0
        self._resolver_cache_misses = 0
        self._resolver_negative_cache_hits = 0
        self._resolver_circuit_open_rejections = 0
        self._resolver_recovery_attempts = 0
        self._resolver_recovery_succeeded = 0
        self._resolver_recovery_failed = 0

    def configure_torbox_budget(self, requests_per_minute: int) -> None:
        with self._lock:
            self._request_budget = requests_per_minute

    def torbox_queue_entered(self) -> None:
        with self._lock:
            self._queue_depth += 1

    def torbox_queue_left(self) -> None:
        with self._lock:
            self._queue_depth = max(0, self._queue_depth - 1)

    def torbox_request_started(self) -> None:
        with self._lock:
            now = self._clock()
            self._requests_total += 1
            self._recent_calls.append(now)
            self._prune_recent_calls(now)

    def torbox_request_finished(self, *, status_code: int | None, succeeded: bool) -> None:
        with self._lock:
            if succeeded:
                self._requests_succeeded += 1
            else:
                self._requests_failed += 1
            if status_code == HTTP_TOO_MANY_REQUESTS:
                self._responses_429 += 1

    def resolver_cache_hit(self) -> None:
        with self._lock:
            self._resolver_cache_hits += 1

    def resolver_cache_miss(self) -> None:
        with self._lock:
            self._resolver_cache_misses += 1

    def resolver_negative_cache_hit(self) -> None:
        with self._lock:
            self._resolver_negative_cache_hits += 1

    def resolver_circuit_open_rejection(self) -> None:
        with self._lock:
            self._resolver_circuit_open_rejections += 1

    def resolver_recovery_started(self) -> None:
        with self._lock:
            self._resolver_recovery_attempts += 1

    def resolver_recovery_finished(self, *, succeeded: bool) -> None:
        with self._lock:
            if succeeded:
                self._resolver_recovery_succeeded += 1
            else:
                self._resolver_recovery_failed += 1

    def snapshot(self) -> OperationalMetricsSnapshot:
        with self._lock:
            now = self._clock()
            self._prune_recent_calls(now)
            return OperationalMetricsSnapshot(
                torbox_request_budget_per_minute=self._request_budget,
                torbox_requests_total=self._requests_total,
                torbox_requests_succeeded=self._requests_succeeded,
                torbox_requests_failed=self._requests_failed,
                torbox_responses_429=self._responses_429,
                torbox_calls_last_minute=len(self._recent_calls),
                torbox_queue_depth=self._queue_depth,
                resolver_cache_hits=self._resolver_cache_hits,
                resolver_cache_misses=self._resolver_cache_misses,
                resolver_negative_cache_hits=self._resolver_negative_cache_hits,
                resolver_circuit_open_rejections=self._resolver_circuit_open_rejections,
                resolver_recovery_attempts=self._resolver_recovery_attempts,
                resolver_recovery_succeeded=self._resolver_recovery_succeeded,
                resolver_recovery_failed=self._resolver_recovery_failed,
            )

    def reset(self) -> None:
        with self._lock:
            self._requests_total = 0
            self._requests_succeeded = 0
            self._requests_failed = 0
            self._responses_429 = 0
            self._queue_depth = 0
            self._recent_calls.clear()
            self._resolver_cache_hits = 0
            self._resolver_cache_misses = 0
            self._resolver_negative_cache_hits = 0
            self._resolver_circuit_open_rejections = 0
            self._resolver_recovery_attempts = 0
            self._resolver_recovery_succeeded = 0
            self._resolver_recovery_failed = 0

    def _prune_recent_calls(self, now: float) -> None:
        cutoff = now - RECENT_CALL_WINDOW_SECONDS
        while self._recent_calls and self._recent_calls[0] <= cutoff:
            _ = self._recent_calls.popleft()


_operational_metrics = OperationalMetrics()


def get_operational_metrics() -> OperationalMetrics:
    return _operational_metrics
