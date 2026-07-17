from datetime import timedelta
from typing import cast

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TmdbCacheEntry, utc_now
from app.db.repositories.tmdb_cache import TmdbCacheRepository
from app.providers.tmdb.cache_keys import tmdb_cache_key
from app.providers.tmdb.client import TmdbClient, TmdbClientError
from app.providers.tmdb.metadata import (
    SEASON_COMPLETION_TMDB_CACHE_TTL,
    TmdbMetadataService,
)


class FakeResult:
    def __init__(self, scalar: object | None = None) -> None:
        self._scalar = scalar

    def scalar_one_or_none(self) -> object | None:
        return self._scalar


class FakeSession:
    def __init__(self, results: list[FakeResult]) -> None:
        self._results = results
        self.added: list[object] = []
        self.committed = False

    async def execute(self, statement: object) -> FakeResult:
        _ = statement
        return self._results.pop(0)

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        self.committed = True


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


def test_tmdb_cache_key_sorts_params_and_excludes_api_key() -> None:
    assert tmdb_cache_key(
        "/search/movie", {"query": "Alien", "api_key": "secret", "year": "1979"}
    ) == ('tmdb:v1:GET:/search/movie:{"query":"Alien","year":"1979"}')


@pytest.mark.asyncio
async def test_tmdb_client_uses_bearer_token_without_storing_secret_in_url() -> None:
    seen_urls: list[str] = []
    seen_headers: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        seen_headers.append(request.headers.get("authorization"))
        return httpx.Response(200, json={"results": []})

    payload = await TmdbClient(
        api_key="eyJvYXV0aC10b2tlbiJ9.payload.signature",
        base_url="https://api.themoviedb.org/3",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    ).get_json("/search/movie", params={"query": "Alien"})

    assert payload == {"results": []}
    assert seen_urls == ["https://api.themoviedb.org/3/search/movie?query=Alien"]
    assert seen_headers == ["Bearer eyJvYXV0aC10b2tlbiJ9.payload.signature"]


@pytest.mark.asyncio
async def test_tmdb_client_uses_v3_api_key_query_param_without_a_401_retry() -> None:
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(200, json={"results": []})

    payload = await TmdbClient(
        api_key="39647d09ad21d4536609cd28f0f50c14",
        base_url="https://api.themoviedb.org/3",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    ).get_json("/search/movie", params={"query": "Alien"})

    assert payload == {"results": []}
    assert seen_urls == [
        "https://api.themoviedb.org/3/search/movie?query=Alien&api_key=39647d09ad21d4536609cd28f0f50c14"
    ]


@pytest.mark.asyncio
async def test_tmdb_client_error_does_not_expose_api_key() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"status_message": "failure"})

    with pytest.raises(TmdbClientError) as error:
        _ = await TmdbClient(
            api_key="tmdb-secret",
            base_url="https://api.themoviedb.org/3",
            timeout_seconds=5,
            transport=httpx.MockTransport(handler),
        ).get_json("/search/movie", params={"query": "Alien"})

    assert "tmdb-secret" not in str(error.value)


@pytest.mark.asyncio
async def test_tmdb_cache_repository_returns_fresh_payload() -> None:
    now = utc_now()
    cache_entry = TmdbCacheEntry(
        cache_key="key",
        endpoint="/configuration",
        request_params={},
        response_payload={"images": {}},
        fetched_at=now,
        expires_at=now + timedelta(hours=1),
    )
    session = FakeSession([FakeResult(scalar=cache_entry)])

    cached = await TmdbCacheRepository(cast(AsyncSession, session)).get_fresh("key", now=now)

    assert cached is not None
    assert cached.response_payload == {"images": {}}


@pytest.mark.asyncio
async def test_tmdb_cache_repository_ignores_expired_payload() -> None:
    now = utc_now()
    cache_entry = TmdbCacheEntry(
        cache_key="key",
        endpoint="/configuration",
        request_params={},
        response_payload={"images": {}},
        fetched_at=now - timedelta(days=2),
        expires_at=now - timedelta(seconds=1),
    )
    session = FakeSession([FakeResult(scalar=cache_entry)])

    cached = await TmdbCacheRepository(cast(AsyncSession, session)).get_fresh("key", now=now)

    assert cached is None


@pytest.mark.asyncio
async def test_tmdb_cache_repository_stores_payload_without_secret_params() -> None:
    session = FakeSession([FakeResult(scalar=None)])
    repository = TmdbCacheRepository(cast(AsyncSession, session))

    await repository.store(
        cache_key="key",
        endpoint="/search/movie",
        request_params={"query": "Alien", "api_key": "secret"},
        response_payload={"results": []},
        ttl=timedelta(days=7),
    )

    cache_entry = next(item for item in session.added if isinstance(item, TmdbCacheEntry))
    assert cache_entry.request_params == {"query": "Alien"}
    assert "secret" not in str(cache_entry.response_payload)


@pytest.mark.asyncio
async def test_tmdb_metadata_service_uses_database_cache_before_network() -> None:
    now = utc_now()
    cache_entry = TmdbCacheEntry(
        cache_key=tmdb_cache_key("/configuration", {}),
        endpoint="/configuration",
        request_params={},
        response_payload={"images": {"secure_base_url": "https://image.tmdb.org/t/p/"}},
        fetched_at=now,
        expires_at=now + timedelta(hours=1),
    )
    session = FakeSession([FakeResult(scalar=cache_entry)])
    client = FakeTmdbClient({"images": {}})

    payload = await TmdbMetadataService(
        cache_repository=TmdbCacheRepository(cast(AsyncSession, session)),
        tmdb_client=client,
    ).get_json("/configuration")

    assert payload == {"images": {"secure_base_url": "https://image.tmdb.org/t/p/"}}
    assert client.calls == []


@pytest.mark.asyncio
async def test_tmdb_metadata_service_fetches_and_caches_misses() -> None:
    session = FakeSession([FakeResult(scalar=None), FakeResult(scalar=None)])
    client = FakeTmdbClient({"results": [{"id": 1, "title": "Alien"}]})

    payload = await TmdbMetadataService(
        cache_repository=TmdbCacheRepository(cast(AsyncSession, session)),
        tmdb_client=client,
    ).get_json("/search/movie", params={"query": "Alien"})

    assert payload == {"results": [{"id": 1, "title": "Alien"}]}
    assert client.calls == [("/search/movie", {"query": "Alien"})]
    assert session.committed is False


@pytest.mark.asyncio
async def test_season_completion_metadata_uses_a_one_year_cache() -> None:
    session = FakeSession([FakeResult(scalar=None), FakeResult(scalar=None)])
    client = FakeTmdbClient({"episodes": []})

    _ = await TmdbMetadataService(
        cache_repository=TmdbCacheRepository(cast(AsyncSession, session)),
        tmdb_client=client,
    ).get_season_completion_json("/tv/220074/season/1")

    cache_entry = next(item for item in session.added if isinstance(item, TmdbCacheEntry))
    assert cache_entry.expires_at - cache_entry.fetched_at == SEASON_COMPLETION_TMDB_CACHE_TTL
