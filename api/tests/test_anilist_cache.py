import json
from datetime import timedelta
from typing import Any, cast

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AniListCacheEntry, utc_now
from app.db.repositories.anilist_cache import AniListCacheRepository
from app.providers.anilist.anime import ANILIST_ANIME_SEARCH_QUERY, AniListAnimeService
from app.providers.anilist.cache_keys import anilist_cache_key
from app.providers.anilist.client import AniListClient, AniListClientError


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


class FakeAniListClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict[str, Any], str | None]] = []

    async def execute(
        self,
        *,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append((query, variables or {}, operation_name))
        return self.payload


def test_anilist_cache_key_is_stable_for_graphql_payloads() -> None:
    first = anilist_cache_key(
        operation_name="SearchAnime",
        query="query SearchAnime { Page { media { id } } }",
        variables={"search": "Frieren", "perPage": 5},
    )
    second = anilist_cache_key(
        operation_name="SearchAnime",
        query="query   SearchAnime {   Page { media { id } } }",
        variables={"perPage": 5, "search": "Frieren"},
    )

    assert first == second
    assert first.startswith("anilist:v1:POST:")


@pytest.mark.asyncio
async def test_anilist_client_posts_graphql_payload() -> None:
    seen_payloads: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_payloads.append(cast(dict[str, Any], json.loads(request.content)))
        return httpx.Response(200, json={"data": {"Page": {"media": []}}})

    payload = await AniListClient(
        base_url="https://graphql.anilist.co",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    ).execute(
        query="query SearchAnime($search: String!) { Page { media(search: $search) { id } } }",
        variables={"search": "Frieren"},
        operation_name="SearchAnime",
    )

    assert payload == {"data": {"Page": {"media": []}}}
    assert seen_payloads[0]["operationName"] == "SearchAnime"
    assert seen_payloads[0]["variables"] == {"search": "Frieren"}


@pytest.mark.asyncio
async def test_anilist_client_error_is_safe() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"errors": [{"message": "bad query"}]})

    with pytest.raises(AniListClientError) as error:
        _ = await AniListClient(
            base_url="https://graphql.anilist.co",
            timeout_seconds=5,
            transport=httpx.MockTransport(handler),
        ).execute(query="query Broken { nope }", operation_name="Broken")

    assert "bad query" not in str(error.value)


@pytest.mark.asyncio
async def test_anilist_cache_repository_returns_fresh_payload() -> None:
    now = utc_now()
    cache_entry = AniListCacheEntry(
        cache_key="key",
        operation_name="SearchAnime",
        query="query SearchAnime { Page { media { id } } }",
        variables={"search": "Frieren"},
        response_payload={"data": {"Page": {"media": []}}},
        fetched_at=now,
        expires_at=now + timedelta(hours=1),
    )
    session = FakeSession([FakeResult(scalar=cache_entry)])

    cached = await AniListCacheRepository(cast(AsyncSession, session)).get_fresh("key", now=now)

    assert cached is not None
    assert cached.response_payload == {"data": {"Page": {"media": []}}}


@pytest.mark.asyncio
async def test_anilist_cache_repository_ignores_expired_payload() -> None:
    now = utc_now()
    cache_entry = AniListCacheEntry(
        cache_key="key",
        operation_name="SearchAnime",
        query="query SearchAnime { Page { media { id } } }",
        variables={"search": "Frieren"},
        response_payload={"data": {"Page": {"media": []}}},
        fetched_at=now - timedelta(days=2),
        expires_at=now - timedelta(seconds=1),
    )
    session = FakeSession([FakeResult(scalar=cache_entry)])

    cached = await AniListCacheRepository(cast(AsyncSession, session)).get_fresh("key", now=now)

    assert cached is None


@pytest.mark.asyncio
async def test_anilist_anime_service_uses_database_cache_before_network() -> None:
    now = utc_now()
    cache_entry = AniListCacheEntry(
        cache_key=anilist_cache_key(
            operation_name="SearchAnime",
            query=_search_query(),
            variables={"search": "Frieren", "page": 1, "perPage": 5, "seasonYear": 2023},
        ),
        operation_name="SearchAnime",
        query=_search_query(),
        variables={"search": "Frieren", "page": 1, "perPage": 5, "seasonYear": 2023},
        response_payload=_anime_payload(year=2023),
        fetched_at=now,
        expires_at=now + timedelta(hours=1),
    )
    session = FakeSession([FakeResult(scalar=cache_entry)])
    client = FakeAniListClient({"data": {"Page": {"media": []}}})

    is_anime = await AniListAnimeService(
        cache_repository=AniListCacheRepository(cast(AsyncSession, session)),
        anilist_client=client,
    ).has_anime_match("Frieren", year=2023)

    assert is_anime is True
    assert client.calls == []


@pytest.mark.asyncio
async def test_anilist_anime_service_fetches_and_caches_misses() -> None:
    session = FakeSession([FakeResult(scalar=None), FakeResult(scalar=None)])
    client = FakeAniListClient(_anime_payload(year=2023))

    payload = await AniListAnimeService(
        cache_repository=AniListCacheRepository(cast(AsyncSession, session)),
        anilist_client=client,
    ).search_anime("Frieren", year=2023)

    assert payload == _anime_payload(year=2023)
    assert len(client.calls) == 1
    assert session.committed is False
    cache_entry = next(item for item in session.added if isinstance(item, AniListCacheEntry))
    assert cache_entry.variables == {
        "search": "Frieren",
        "page": 1,
        "perPage": 5,
        "seasonYear": 2023,
    }


@pytest.mark.asyncio
async def test_anilist_anime_service_rejects_non_matching_year() -> None:
    session = FakeSession([FakeResult(scalar=None), FakeResult(scalar=None)])
    client = FakeAniListClient(_anime_payload(year=2020))

    is_anime = await AniListAnimeService(
        cache_repository=AniListCacheRepository(cast(AsyncSession, session)),
        anilist_client=client,
    ).has_anime_match("Frieren", year=2023)

    assert is_anime is False


@pytest.mark.asyncio
async def test_anilist_anime_service_rejects_non_matching_title() -> None:
    session = FakeSession([FakeResult(scalar=None), FakeResult(scalar=None)])
    client = FakeAniListClient(_anime_payload(year=2023))

    is_anime = await AniListAnimeService(
        cache_repository=AniListCacheRepository(cast(AsyncSession, session)),
        anilist_client=client,
    ).has_anime_match("Unrelated Show", year=2023)

    assert is_anime is False


@pytest.mark.asyncio
async def test_anilist_anime_service_accepts_season_title_variant() -> None:
    session = FakeSession([FakeResult(scalar=None), FakeResult(scalar=None)])
    client = FakeAniListClient(
        _anime_payload_with_title(
            english="Ascendance of a Bookworm Season 3",
            romaji="Honzuki no Gekokujou: Shisho ni Naru Tame ni wa Shudan wo Erandeiraremasen",
            year=2022,
        )
    )

    is_anime = await AniListAnimeService(
        cache_repository=AniListCacheRepository(cast(AsyncSession, session)),
        anilist_client=client,
    ).has_anime_match("Ascendance of a Bookworm", year=2022)

    assert is_anime is True


@pytest.mark.asyncio
async def test_anilist_anime_service_accepts_dated_subtitle_variant() -> None:
    session = FakeSession([FakeResult(scalar=None), FakeResult(scalar=None)])
    client = FakeAniListClient(
        _anime_payload_with_title(
            english="Ascendance of a Bookworm: I'll Stop at Nothing to Become a Librarian",
            romaji="Honzuki no Gekokujou",
            year=2022,
        )
    )

    is_anime = await AniListAnimeService(
        cache_repository=AniListCacheRepository(cast(AsyncSession, session)),
        anilist_client=client,
    ).has_anime_match("Ascendance of a Bookworm", year=2022)

    assert is_anime is True


@pytest.mark.asyncio
async def test_anilist_anime_service_rejects_unmarked_prefix_match() -> None:
    session = FakeSession([FakeResult(scalar=None), FakeResult(scalar=None)])
    client = FakeAniListClient(
        _anime_payload_with_title(
            english="Ascendance of a Bookwormish Archive",
            romaji="Unrelated Anime",
            year=2022,
        )
    )

    is_anime = await AniListAnimeService(
        cache_repository=AniListCacheRepository(cast(AsyncSession, session)),
        anilist_client=client,
    ).has_anime_match("Ascendance of a Bookworm", year=2022)

    assert is_anime is False


def _anime_payload(*, year: int) -> dict[str, Any]:
    return {
        "data": {
            "Page": {
                "media": [
                    {
                        "id": 154587,
                        "title": {"romaji": "Sousou no Frieren", "english": "Frieren"},
                        "startDate": {"year": year},
                        "isAdult": False,
                    }
                ]
            }
        }
    }


def _anime_payload_with_title(*, english: str, romaji: str, year: int) -> dict[str, Any]:
    return {
        "data": {
            "Page": {
                "media": [
                    {
                        "id": 42424,
                        "title": {"romaji": romaji, "english": english},
                        "startDate": {"year": year},
                        "isAdult": False,
                    }
                ]
            }
        }
    }


def _search_query() -> str:
    return ANILIST_ANIME_SEARCH_QUERY
