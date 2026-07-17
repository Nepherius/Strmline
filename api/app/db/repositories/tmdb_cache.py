from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TmdbCacheEntry, utc_now


@dataclass(frozen=True, slots=True)
class TmdbCacheRecord:
    response_payload: dict[str, Any]
    fetched_at: datetime
    expires_at: datetime


class TmdbCacheRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_fresh(
        self,
        cache_key: str,
        *,
        now: datetime | None = None,
    ) -> TmdbCacheRecord | None:
        checked_at = now or utc_now()
        result = await self._session.execute(
            select(TmdbCacheEntry).where(TmdbCacheEntry.cache_key == cache_key)
        )
        cache_entry = result.scalar_one_or_none()
        if cache_entry is None or cache_entry.expires_at <= checked_at:
            return None
        return TmdbCacheRecord(
            response_payload=cache_entry.response_payload,
            fetched_at=cache_entry.fetched_at,
            expires_at=cache_entry.expires_at,
        )

    async def store(
        self,
        *,
        cache_key: str,
        endpoint: str,
        request_params: dict[str, str],
        response_payload: dict[str, Any],
        ttl: timedelta,
        now: datetime | None = None,
    ) -> None:
        fetched_at = now or utc_now()
        safe_params = _safe_request_params(request_params)
        result = await self._session.execute(
            select(TmdbCacheEntry).where(TmdbCacheEntry.cache_key == cache_key)
        )
        cache_entry = result.scalar_one_or_none()
        if cache_entry is None:
            self._session.add(
                TmdbCacheEntry(
                    cache_key=cache_key,
                    endpoint=endpoint,
                    request_params=safe_params,
                    response_payload=response_payload,
                    fetched_at=fetched_at,
                    expires_at=fetched_at + ttl,
                )
            )
            await self._session.flush()
            return

        cache_entry.endpoint = endpoint
        cache_entry.request_params = safe_params
        cache_entry.response_payload = response_payload
        cache_entry.fetched_at = fetched_at
        cache_entry.expires_at = fetched_at + ttl
        await self._session.flush()


def _safe_request_params(params: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in params.items() if key.lower() != "api_key"}
