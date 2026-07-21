import pytest

from app.operations.metrics import OperationalMetrics
from app.resolver.failure_guard import (
    ResolverFailureGuard,
    ResolverFailureGuardConfig,
    ResolverTemporarilyUnavailableError,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _guard(clock: FakeClock, metrics: OperationalMetrics) -> ResolverFailureGuard:
    return ResolverFailureGuard(
        ResolverFailureGuardConfig(
            negative_cache_seconds=30,
            circuit_failures=3,
            circuit_window_seconds=120,
            circuit_cooldown_seconds=60,
        ),
        metrics=metrics,
        clock=clock,
    )


def test_failure_guard_negative_caches_recent_failure() -> None:
    clock = FakeClock()
    metrics = OperationalMetrics(clock=clock)
    guard = _guard(clock, metrics)

    guard.record_failure("entry")
    with pytest.raises(ResolverTemporarilyUnavailableError, match="recently failed"):
        guard.check("entry")

    clock.advance(30)
    guard.check("entry")
    assert metrics.snapshot().resolver_negative_cache_hits == 1


def test_failure_guard_opens_and_recovers_per_entry_circuit() -> None:
    clock = FakeClock()
    metrics = OperationalMetrics(clock=clock)
    guard = _guard(clock, metrics)

    for _ in range(3):
        guard.record_failure("entry")
        clock.advance(30)

    with pytest.raises(ResolverTemporarilyUnavailableError, match="temporarily paused"):
        guard.check("entry")
    guard.check("other-entry")

    clock.advance(30)
    guard.check("entry")
    guard.record_success("entry")
    assert metrics.snapshot().resolver_circuit_open_rejections == 1
