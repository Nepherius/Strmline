from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app.db.repositories.library_health import LibraryHealthSource, LibraryHealthStatus


class LibraryHealthStore(Protocol):
    async def active_sources(self) -> tuple[LibraryHealthSource, ...]: ...

    async def persist(
        self,
        sources: tuple[LibraryHealthSource, ...],
        statuses: dict[int, LibraryHealthStatus],
        *,
        checked_at: datetime,
    ) -> None: ...


class TorBoxHealthClient(Protocol):
    async def find_torrents_by_hashes(
        self,
        info_hashes: set[str],
    ) -> dict[str, dict[str, Any]]: ...

    async def check_cached_strict(self, hashes: list[str]) -> dict[str, bool]: ...


@dataclass(frozen=True, slots=True)
class LibraryHealthCheckResult:
    checked_at: datetime
    checked_entries: int
    distinct_hashes: int
    ready: int
    recoverable: int
    unavailable: int
    unknown: int


async def check_library_health(
    repository: LibraryHealthStore,
    torbox_client: TorBoxHealthClient,
    *,
    checked_at: datetime | None = None,
) -> LibraryHealthCheckResult:
    sources = await repository.active_sources()
    hashes = sorted(
        {
            source.info_hash
            for source in sources
            if source.source_kind == "torrents" and source.info_hash is not None
        }
    )
    current = await torbox_client.find_torrents_by_hashes(set(hashes))
    missing_hashes = [info_hash for info_hash in hashes if info_hash not in current]
    cached = await torbox_client.check_cached_strict(missing_hashes)
    statuses: dict[int, LibraryHealthStatus] = {
        source.library_entry_id: _source_status(source, current, cached) for source in sources
    }
    finished_at = checked_at or datetime.now(UTC)
    await repository.persist(sources, statuses, checked_at=finished_at)
    counts: dict[LibraryHealthStatus, int] = {
        "ready": 0,
        "recoverable": 0,
        "unavailable": 0,
        "unknown": 0,
    }
    for status in statuses.values():
        counts[status] += 1
    return LibraryHealthCheckResult(
        checked_at=finished_at,
        checked_entries=len(sources),
        distinct_hashes=len(hashes),
        ready=counts["ready"],
        recoverable=counts["recoverable"],
        unavailable=counts["unavailable"],
        unknown=counts["unknown"],
    )


def _source_status(
    source: LibraryHealthSource,
    current: dict[str, dict[str, Any]],
    cached: dict[str, bool],
) -> LibraryHealthStatus:
    if source.source_kind != "torrents" or source.info_hash is None:
        return "unknown"
    if source.info_hash in current:
        return "ready"
    if cached.get(source.info_hash, False):
        return "recoverable"
    return "unavailable"
