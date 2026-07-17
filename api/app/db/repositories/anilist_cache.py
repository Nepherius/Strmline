from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AniListCacheEntry, utc_now


@dataclass(frozen=True, slots=True)
class AniListCacheRecord:
    response_payload: dict[str, Any]
    fetched_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class AniListCacheWrite:
    operation_name: str
    query: str
    variables: dict[str, Any]
    response_payload: dict[str, Any]


class AniListCacheRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_fresh(
        self,
        cache_key: str,
        *,
        now: datetime | None = None,
    ) -> AniListCacheRecord | None:
        checked_at = now or utc_now()
        result = await self._session.execute(
            select(AniListCacheEntry).where(AniListCacheEntry.cache_key == cache_key)
        )
        cache_entry = result.scalar_one_or_none()
        if cache_entry is None or cache_entry.expires_at <= checked_at:
            return None
        return AniListCacheRecord(
            response_payload=cache_entry.response_payload,
            fetched_at=cache_entry.fetched_at,
            expires_at=cache_entry.expires_at,
        )

    async def store(
        self,
        *,
        cache_key: str,
        cache_write: AniListCacheWrite,
        ttl: timedelta,
        now: datetime | None = None,
    ) -> None:
        fetched_at = now or utc_now()
        result = await self._session.execute(
            select(AniListCacheEntry).where(AniListCacheEntry.cache_key == cache_key)
        )
        cache_entry = result.scalar_one_or_none()
        if cache_entry is None:
            self._session.add(
                AniListCacheEntry(
                    cache_key=cache_key,
                    operation_name=cache_write.operation_name,
                    query=cache_write.query,
                    variables=cache_write.variables,
                    response_payload=cache_write.response_payload,
                    fetched_at=fetched_at,
                    expires_at=fetched_at + ttl,
                )
            )
            await self._session.flush()
            return

        cache_entry.operation_name = cache_write.operation_name
        cache_entry.query = cache_write.query
        cache_entry.variables = cache_write.variables
        cache_entry.response_payload = cache_write.response_payload
        cache_entry.fetched_at = fetched_at
        cache_entry.expires_at = fetched_at + ttl
        await self._session.flush()
