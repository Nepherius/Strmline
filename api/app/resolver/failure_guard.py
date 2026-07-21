from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from time import monotonic

from app.operations.defaults import (
    RESOLVER_CIRCUIT_BREAKER_COOLDOWN_SECONDS,
    RESOLVER_CIRCUIT_BREAKER_FAILURES,
    RESOLVER_CIRCUIT_BREAKER_WINDOW_SECONDS,
    RESOLVER_NEGATIVE_CACHE_SECONDS,
)
from app.operations.metrics import OperationalMetrics, get_operational_metrics


class ResolverTemporarilyUnavailableError(RuntimeError):
    """Raised when recent upstream failures suppress another recovery attempt."""


@dataclass(slots=True)
class _FailureState:
    failures: deque[float]
    circuit_open_until: float = 0.0


@dataclass(frozen=True, slots=True)
class ResolverFailureGuardConfig:
    negative_cache_seconds: float = RESOLVER_NEGATIVE_CACHE_SECONDS
    circuit_failures: int = RESOLVER_CIRCUIT_BREAKER_FAILURES
    circuit_window_seconds: float = RESOLVER_CIRCUIT_BREAKER_WINDOW_SECONDS
    circuit_cooldown_seconds: float = RESOLVER_CIRCUIT_BREAKER_COOLDOWN_SECONDS
    max_entries: int = 2_048


class ResolverFailureGuard:
    """Bound repeated resolver failures with a negative cache and circuit breaker."""

    def __init__(
        self,
        config: ResolverFailureGuardConfig,
        *,
        metrics: OperationalMetrics | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._validate_config(config)
        self._config = config
        self._metrics = metrics or get_operational_metrics()
        self._clock = clock
        self._lock = Lock()
        self._negative_until: dict[str, float] = {}
        self._failure_states: dict[str, _FailureState] = {}

    def reconfigure(self, config: ResolverFailureGuardConfig) -> None:
        self._validate_config(config)
        with self._lock:
            self._config = config
            self._negative_until.clear()
            self._failure_states.clear()

    def check(self, entry_id: str) -> None:
        with self._lock:
            now = self._clock()
            state = self._failure_states.get(entry_id)
            if state is not None and state.circuit_open_until > now:
                self._metrics.resolver_circuit_open_rejection()
                msg = "Playback recovery is temporarily paused after repeated upstream failures."
                raise ResolverTemporarilyUnavailableError(msg)
            negative_until = self._negative_until.get(entry_id, 0.0)
            if negative_until > now:
                self._metrics.resolver_negative_cache_hit()
                msg = "Playback recovery recently failed; retry shortly."
                raise ResolverTemporarilyUnavailableError(msg)
            _ = self._negative_until.pop(entry_id, None)
            if state is not None:
                self._prune_failures(state, now)

    def record_failure(self, entry_id: str) -> None:
        with self._lock:
            now = self._clock()
            self._negative_until[entry_id] = now + self._config.negative_cache_seconds
            state = self._failure_states.setdefault(entry_id, _FailureState(deque()))
            self._prune_failures(state, now)
            state.failures.append(now)
            if len(state.failures) >= self._config.circuit_failures:
                state.circuit_open_until = now + self._config.circuit_cooldown_seconds
            self._evict_if_needed()

    def record_success(self, entry_id: str) -> None:
        with self._lock:
            _ = self._negative_until.pop(entry_id, None)
            _ = self._failure_states.pop(entry_id, None)

    def clear(self) -> None:
        with self._lock:
            self._negative_until.clear()
            self._failure_states.clear()

    def _prune_failures(self, state: _FailureState, now: float) -> None:
        cutoff = now - self._config.circuit_window_seconds
        while state.failures and state.failures[0] <= cutoff:
            _ = state.failures.popleft()
        if state.circuit_open_until <= now:
            state.circuit_open_until = 0.0

    def _evict_if_needed(self) -> None:
        while len(self._failure_states) > self._config.max_entries:
            oldest_key = next(iter(self._failure_states))
            _ = self._failure_states.pop(oldest_key, None)
            _ = self._negative_until.pop(oldest_key, None)

    @staticmethod
    def _validate_config(config: ResolverFailureGuardConfig) -> None:
        if config.negative_cache_seconds <= 0 or config.circuit_window_seconds <= 0:
            msg = "Resolver failure guard durations must be positive."
            raise ValueError(msg)
        if (
            config.circuit_failures <= 0
            or config.circuit_cooldown_seconds <= 0
            or config.max_entries <= 0
        ):
            msg = "Resolver failure guard limits must be positive."
            raise ValueError(msg)
