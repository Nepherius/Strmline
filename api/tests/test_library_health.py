from datetime import UTC, datetime
from typing import Any

import pytest

from app.db.repositories.library_health import LibraryHealthSource, LibraryHealthStatus
from app.library.health import check_library_health


class FakeHealthRepository:
    def __init__(self, sources: tuple[LibraryHealthSource, ...]) -> None:
        self.sources = sources
        self.persisted: dict[int, LibraryHealthStatus] | None = None
        self.checked_at: datetime | None = None

    async def active_sources(self) -> tuple[LibraryHealthSource, ...]:
        return self.sources

    async def persist(
        self,
        sources: tuple[LibraryHealthSource, ...],
        statuses: dict[int, LibraryHealthStatus],
        *,
        checked_at: datetime,
    ) -> None:
        assert sources == self.sources
        self.persisted = statuses
        self.checked_at = checked_at


class FakeTorBoxClient:
    def __init__(self) -> None:
        self.requested_current: set[str] | None = None
        self.requested_cached: list[str] | None = None

    async def find_torrents_by_hashes(
        self,
        info_hashes: set[str],
    ) -> dict[str, dict[str, Any]]:
        self.requested_current = info_hashes
        return {"ready-hash": {"id": 1}}

    async def check_cached_strict(self, hashes: list[str]) -> dict[str, bool]:
        self.requested_cached = hashes
        return {
            "ready-hash": True,
            "recoverable-hash": True,
            "missing-hash": False,
        }


@pytest.mark.asyncio
async def test_health_check_classifies_sources_and_deduplicates_hashes() -> None:
    checked_at = datetime(2026, 7, 18, 12, tzinfo=UTC)
    repository = FakeHealthRepository(
        (
            LibraryHealthSource(1, "torrents", "ready-hash"),
            LibraryHealthSource(2, "torrents", "ready-hash"),
            LibraryHealthSource(3, "torrents", "recoverable-hash"),
            LibraryHealthSource(4, "torrents", "missing-hash"),
            LibraryHealthSource(5, "usenet", None),
        )
    )
    client = FakeTorBoxClient()

    result = await check_library_health(repository, client, checked_at=checked_at)

    assert client.requested_current == {"ready-hash", "recoverable-hash", "missing-hash"}
    assert client.requested_cached == ["missing-hash", "recoverable-hash"]
    assert repository.persisted == {
        1: "ready",
        2: "ready",
        3: "recoverable",
        4: "unavailable",
        5: "unknown",
    }
    assert repository.checked_at == checked_at
    assert result.checked_entries == 5
    assert result.distinct_hashes == 3
    assert (result.ready, result.recoverable, result.unavailable, result.unknown) == (2, 1, 1, 1)
