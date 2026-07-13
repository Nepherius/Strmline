from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Protocol

from app.db.repositories.tmdb_cache import TmdbCacheRepository
from app.providers.tmdb.cache_keys import tmdb_cache_key

DEFAULT_TMDB_CACHE_TTL = timedelta(days=7)
SEASON_COMPLETION_TMDB_CACHE_TTL = timedelta(days=365)
logger = logging.getLogger(__name__)


class TmdbJsonClient(Protocol):
    async def get_json(
        self,
        endpoint: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]: ...


class TmdbMetadataService:
    def __init__(
        self,
        *,
        cache_repository: TmdbCacheRepository,
        tmdb_client: TmdbJsonClient,
    ) -> None:
        self._cache_repository = cache_repository
        self._tmdb_client = tmdb_client

    async def get_json(
        self,
        endpoint: str,
        *,
        params: dict[str, str] | None = None,
        ttl: timedelta = DEFAULT_TMDB_CACHE_TTL,
    ) -> dict[str, Any]:
        request_params = params or {}
        cache_key = tmdb_cache_key(endpoint, request_params)
        cached = await self._cache_repository.get_fresh(cache_key)
        if cached is not None:
            logger.debug("TMDB metadata cache hit for %s.", endpoint)
            return cached.response_payload

        logger.debug("TMDB metadata cache miss for %s.", endpoint)
        payload = await self._tmdb_client.get_json(endpoint, params=request_params)
        await self._cache_repository.store(
            cache_key=cache_key,
            endpoint=endpoint,
            request_params=request_params,
            response_payload=payload,
            ttl=ttl,
        )
        await self._cache_repository.commit()
        return payload

    async def get_season_completion_json(
        self,
        endpoint: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Load stable series metadata with a long-lived cache for completion jobs."""
        return await self.get_json(
            endpoint,
            params=params,
            ttl=SEASON_COMPLETION_TMDB_CACHE_TTL,
        )
