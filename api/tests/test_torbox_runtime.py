from __future__ import annotations

import httpx
import pytest

from app.operations.metrics import OperationalMetrics
from app.providers.torbox.client import TorBoxAPIError, TorBoxClient
from app.providers.torbox.runtime import TorBoxRequestCoordinator


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.mark.asyncio
async def test_coordinator_enforces_rolling_request_budget() -> None:
    clock = FakeClock()
    metrics = OperationalMetrics(clock=clock)
    coordinator = TorBoxRequestCoordinator(
        2,
        metrics=metrics,
        clock=clock,
        sleep=clock.sleep,
    )

    await coordinator.acquire()
    await coordinator.acquire()
    await coordinator.acquire()

    assert clock.sleeps == [60.0]
    assert metrics.snapshot().torbox_queue_depth == 0


@pytest.mark.asyncio
async def test_client_records_429_as_failed_torbox_request() -> None:
    clock = FakeClock()
    metrics = OperationalMetrics(clock=clock)
    coordinator = TorBoxRequestCoordinator(10, metrics=metrics, clock=clock)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"success": False, "detail": "Slow down"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = TorBoxClient(
            api_key="secret-token",
            http_client=http_client,
            request_coordinator=coordinator,
        )
        with pytest.raises(TorBoxAPIError):
            _ = await client.get_json("/torrents/mylist")

    snapshot = metrics.snapshot()
    assert snapshot.torbox_requests_total == 1
    assert snapshot.torbox_requests_succeeded == 0
    assert snapshot.torbox_requests_failed == 1
    assert snapshot.torbox_responses_429 == 1
    assert snapshot.torbox_calls_last_minute == 1
