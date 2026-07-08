from __future__ import annotations

import time
from datetime import timedelta
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TmdbCacheEntry, utc_now
from app.db.repositories.tmdb_cache import TmdbCacheRepository
from app.providers.tmdb.metadata import TmdbMetadataService
from app.sync.media_identity import MediaIdentityResolver, score_match, title_similarity


class FakeResult:
    def __init__(self, scalar: object | None = None) -> None:
        self._scalar = scalar

    def scalar_one_or_none(self) -> object | None:
        return self._scalar


class FakeSession:
    def __init__(self, results: list[FakeResult]) -> None:
        self._results = results
        self.added: list[object] = []

    async def execute(self, statement: object) -> FakeResult:
        _ = statement
        return self._results.pop(0)

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass


class FakeTmdbClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict[str, str]]] = []

    async def get_json(
        self,
        endpoint: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, object]:
        self.calls.append((endpoint, params or {}))
        return self.payload


@pytest.mark.asyncio
async def test_media_identity_resolver_without_service() -> None:
    resolver = MediaIdentityResolver(None)
    identity = await resolver.resolve("Alien", 1979, "movies")
    assert identity.tmdb_id is None
    assert identity.title == "Alien"
    assert identity.year == 1979
    assert identity.media_type == "movie"


@pytest.mark.asyncio
async def test_media_identity_resolver_cache_hit() -> None:
    now = utc_now()
    cache_entry = TmdbCacheEntry(
        cache_key='tmdb:v1:GET:/search/multi:{"include_adult":"false","query":"Alien"}',
        endpoint="/search/multi",
        request_params={"query": "Alien", "include_adult": "false"},
        response_payload={
            "results": [
                {
                    "id": 101,
                    "media_type": "movie",
                    "title": "Alien",
                    "release_date": "1979-05-25",
                }
            ]
        },
        fetched_at=now,
        expires_at=now + timedelta(days=1),
    )

    # First session execute returns the TmdbCacheEntry (cache hit)
    session = FakeSession([FakeResult(cache_entry)])
    cache_repo = TmdbCacheRepository(cast(AsyncSession, session))
    client = FakeTmdbClient({})
    service = TmdbMetadataService(cache_repository=cache_repo, tmdb_client=client)

    # Delay set to 1 second; if delay occurs, it's a test failure
    resolver = MediaIdentityResolver(service, delay_seconds=1.0)

    start_time = time.monotonic()
    identity = await resolver.resolve("Alien", 1979, "movies")
    duration = time.monotonic() - start_time

    assert duration < 0.5  # Bypasses delay since it's a cache hit
    assert identity.tmdb_id == "101"
    assert identity.title == "Alien"
    assert identity.year == 1979
    assert identity.media_type == "movie"
    assert len(client.calls) == 0


@pytest.mark.asyncio
async def test_media_identity_resolver_cache_miss_and_memory_cache() -> None:
    # 1. resolver._do_resolve -> cache_repo.get_fresh -> execute (returns None)
    # 2. metadata_service.get_json -> cache_repo.get_fresh -> execute (returns None)
    # 3. metadata_service.get_json -> cache_repo.store -> execute (returns None)
    session = FakeSession([FakeResult(None), FakeResult(None), FakeResult(None)])
    cache_repo = TmdbCacheRepository(cast(AsyncSession, session))
    client = FakeTmdbClient(
        {
            "results": [
                {
                    "id": 202,
                    "media_type": "tv",
                    "name": "Breaking Bad",
                    "first_air_date": "2008-01-20",
                }
            ]
        }
    )
    service = TmdbMetadataService(cache_repository=cache_repo, tmdb_client=client)

    resolver = MediaIdentityResolver(service, delay_seconds=0.01)

    # Resolve first time (will query API and cache in memory)
    identity1 = await resolver.resolve("Breaking Bad", 2008, "shows")
    assert identity1.tmdb_id == "202"
    assert identity1.title == "Breaking Bad"
    assert identity1.year == 2008
    assert identity1.media_type == "tv"
    assert len(client.calls) == 1

    # Resolve second time (should hit in-memory cache)
    identity2 = await resolver.resolve("Breaking Bad", 2008, "shows")
    assert identity2 == identity1
    assert len(client.calls) == 1


def test_title_similarity() -> None:
    assert title_similarity("The King's Warden", "the kings warden") == 1.0
    assert title_similarity("Breaking Bad S01", "Breaking Bad") == pytest.approx(0.6666666)
    assert title_similarity("Alien", "Aliens") == 0.0  # different words


def test_score_match() -> None:
    # Exact match
    assert score_match("Alien", 1979, "movie", "Alien", 1979, "movie") == 1.0
    # Media type mismatch
    assert score_match("Alien", 1979, "movie", "Alien", 1979, "tv") == 0.0
    # Year mismatch > 1
    assert score_match("Alien", 1979, "movie", "Alien", 2026, "movie") == 0.0
    # Year mismatch = 1
    assert score_match("Alien", 1979, "movie", "Alien", 1980, "movie") == 0.5
    # Missing query year
    assert score_match("Alien", None, "movie", "Alien", 1979, "movie") == 0.8


@pytest.mark.asyncio
async def test_media_identity_resolver_exception_fallback() -> None:
    session = FakeSession([FakeResult(None)])
    cache_repo = TmdbCacheRepository(cast(AsyncSession, session))

    class CrashingClient:
        async def get_json(
            self,
            endpoint: str,
            *,
            params: dict[str, str] | None = None,
        ) -> dict[str, Any]:
            _ = endpoint
            _ = params
            raise RuntimeError("API offline")

    service = TmdbMetadataService(
        cache_repository=cache_repo, tmdb_client=cast(Any, CrashingClient())
    )
    resolver = MediaIdentityResolver(service, delay_seconds=0.0)

    # Resolution should catch the error and return fallback safely
    identity = await resolver.resolve("Alien", 1979, "movies")
    assert identity.tmdb_id is None
    assert identity.title == "Alien"
    assert identity.year == 1979
