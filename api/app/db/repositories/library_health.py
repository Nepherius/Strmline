from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import FunctionFilter

from app.db.models import GeneratedFile, LibraryEntry, LibraryEntryHealth

LibraryHealthStatus = Literal["ready", "recoverable", "unavailable", "unknown"]


@dataclass(frozen=True, slots=True)
class LibraryHealthSource:
    library_entry_id: int
    source_kind: str | None
    info_hash: str | None


@dataclass(frozen=True, slots=True)
class LibraryHealthAggregate:
    status: LibraryHealthStatus
    total: int
    ready: int
    recoverable: int
    unavailable: int
    unknown: int
    checked_at: datetime | None


class LibraryHealthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def active_sources(self) -> tuple[LibraryHealthSource, ...]:
        result = await self._session.execute(
            select(
                LibraryEntry.id,
                LibraryEntry.source_kind,
                LibraryEntry.info_hash,
            )
            .join(GeneratedFile, GeneratedFile.library_entry_id == LibraryEntry.id)
            .distinct()
        )
        return tuple(
            LibraryHealthSource(
                library_entry_id=int(library_entry_id),
                source_kind=str(source_kind) if source_kind is not None else None,
                info_hash=str(info_hash).casefold() if info_hash is not None else None,
            )
            for library_entry_id, source_kind, info_hash in result.all()
        )

    async def persist(
        self,
        sources: tuple[LibraryHealthSource, ...],
        statuses: dict[int, LibraryHealthStatus],
        *,
        checked_at: datetime,
    ) -> None:
        entry_ids = [source.library_entry_id for source in sources]
        existing: dict[int, LibraryEntryHealth] = {}
        if entry_ids:
            result = await self._session.execute(
                select(LibraryEntryHealth).where(LibraryEntryHealth.library_entry_id.in_(entry_ids))
            )
            existing = {health.library_entry_id: health for health in result.scalars()}
        for source in sources:
            status = statuses[source.library_entry_id]
            health = existing.get(source.library_entry_id)
            if health is None:
                self._session.add(
                    LibraryEntryHealth(
                        library_entry_id=source.library_entry_id,
                        status=status,
                        info_hash=source.info_hash,
                        checked_at=checked_at,
                    )
                )
                continue
            health.status = status
            health.info_hash = source.info_hash
            health.checked_at = checked_at
        await self._session.flush()

    async def aggregates_for_media(
        self,
        media_keys: set[tuple[int, str]],
    ) -> dict[tuple[int, str], LibraryHealthAggregate]:
        if not media_keys:
            return {}
        valid_health = LibraryEntryHealth.info_hash == LibraryEntry.info_hash

        def status_count(status: LibraryHealthStatus) -> FunctionFilter[int]:
            return func.count(func.distinct(LibraryEntryHealth.library_entry_id)).filter(
                valid_health,
                LibraryEntryHealth.status == status,
            )

        result = await self._session.execute(
            select(
                LibraryEntry.media_item_id,
                LibraryEntry.category,
                func.count(func.distinct(GeneratedFile.id)),
                status_count("ready"),
                status_count("recoverable"),
                status_count("unavailable"),
                func.max(LibraryEntryHealth.checked_at).filter(valid_health),
            )
            .select_from(LibraryEntry)
            .join(GeneratedFile, GeneratedFile.library_entry_id == LibraryEntry.id)
            .outerjoin(
                LibraryEntryHealth,
                LibraryEntryHealth.library_entry_id == LibraryEntry.id,
            )
            .where(tuple_(LibraryEntry.media_item_id, LibraryEntry.category).in_(media_keys))
            .group_by(LibraryEntry.media_item_id, LibraryEntry.category)
        )
        aggregates: dict[tuple[int, str], LibraryHealthAggregate] = {}
        for row in result.all():
            media_item_id, category, total, ready, recoverable, unavailable, checked_at = row
            total_count = int(total)
            ready_count = int(ready)
            recoverable_count = int(recoverable)
            unavailable_count = int(unavailable)
            unknown_count = total_count - ready_count - recoverable_count - unavailable_count
            status = _aggregate_status(
                ready=ready_count,
                recoverable=recoverable_count,
                unavailable=unavailable_count,
                unknown=unknown_count,
            )
            aggregates[(int(media_item_id), str(category))] = LibraryHealthAggregate(
                status=status,
                total=total_count,
                ready=ready_count,
                recoverable=recoverable_count,
                unavailable=unavailable_count,
                unknown=unknown_count,
                checked_at=checked_at if isinstance(checked_at, datetime) else None,
            )
        return aggregates


def _aggregate_status(
    *,
    ready: int,
    recoverable: int,
    unavailable: int,
    unknown: int,
) -> LibraryHealthStatus:
    if unavailable > 0:
        return "unavailable"
    if recoverable > 0:
        return "recoverable"
    if unknown > 0 or ready == 0:
        return "unknown"
    return "ready"
