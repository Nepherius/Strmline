from __future__ import annotations

import re
from datetime import timedelta
from typing import Any, Protocol, cast

from app.db.repositories.anilist_cache import AniListCacheRepository, AniListCacheWrite
from app.providers.anilist.cache_keys import anilist_cache_key

DEFAULT_ANILIST_CACHE_TTL = timedelta(days=7)
ANILIST_ANIME_SEARCH_OPERATION = "SearchAnime"
ANILIST_ANIME_SEARCH_QUERY = """
query SearchAnime($search: String!, $seasonYear: Int, $page: Int!, $perPage: Int!) {
  Page(page: $page, perPage: $perPage) {
    media(search: $search, type: ANIME, seasonYear: $seasonYear, isAdult: false) {
      id
      title {
        romaji
        english
        native
      }
      synonyms
      format
      startDate {
        year
      }
      episodes
      status
      genres
      isAdult
    }
  }
}
"""
SEASON_VARIANT_MARKERS = {"season", "part", "cour", "tv"}
MIN_EXTENDED_VARIANT_TOKENS = 3


class AniListGraphqlClient(Protocol):
    async def execute(
        self,
        *,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> dict[str, Any]: ...


class AniListAnimeService:
    def __init__(
        self,
        *,
        cache_repository: AniListCacheRepository,
        anilist_client: AniListGraphqlClient,
    ) -> None:
        self._cache_repository = cache_repository
        self._anilist_client = anilist_client

    async def search_anime(
        self,
        title: str,
        *,
        year: int | None = None,
        limit: int = 5,
        ttl: timedelta = DEFAULT_ANILIST_CACHE_TTL,
    ) -> dict[str, Any]:
        variables: dict[str, Any] = {
            "search": title,
            "page": 1,
            "perPage": limit,
        }
        if year is not None:
            variables["seasonYear"] = year
        cache_key = anilist_cache_key(
            operation_name=ANILIST_ANIME_SEARCH_OPERATION,
            query=ANILIST_ANIME_SEARCH_QUERY,
            variables=variables,
        )
        cached = await self._cache_repository.get_fresh(cache_key)
        if cached is not None:
            return cached.response_payload

        payload = await self._anilist_client.execute(
            query=ANILIST_ANIME_SEARCH_QUERY,
            variables=variables,
            operation_name=ANILIST_ANIME_SEARCH_OPERATION,
        )
        await self._cache_repository.store(
            cache_key=cache_key,
            cache_write=AniListCacheWrite(
                operation_name=ANILIST_ANIME_SEARCH_OPERATION,
                query=ANILIST_ANIME_SEARCH_QUERY,
                variables=variables,
                response_payload=payload,
            ),
            ttl=ttl,
        )
        await self._cache_repository.commit()
        return payload

    async def has_anime_match(self, title: str, *, year: int | None = None) -> bool:
        payload = await self.search_anime(title, year=year)
        return _has_anime_match(payload, title=title, year=year)


def _has_anime_match(payload: dict[str, Any], *, title: str, year: int | None) -> bool:
    for media_item_value in _media_items_from_payload(payload):
        if _media_item_matches(media_item_value, title=title, year=year):
            return True
    return False


def _media_items_from_payload(payload: dict[str, Any]) -> list[object]:
    data = cast(object, payload.get("data"))
    if not isinstance(data, dict):
        return []
    data_payload = cast(dict[str, object], data)
    page = data_payload.get("Page")
    if not isinstance(page, dict):
        return []
    page_payload = cast(dict[str, object], page)
    media_items = page_payload.get("media")
    if not isinstance(media_items, list):
        return []
    return cast(list[object], media_items)


def _media_item_matches(media_item_value: object, *, title: str, year: int | None) -> bool:
    if not isinstance(media_item_value, dict):
        return False
    media_item = cast(dict[str, object], media_item_value)
    if media_item.get("isAdult") is True:
        return False
    allow_extended_variant = year is not None
    if not _title_matches(media_item, title, allow_extended_variant=allow_extended_variant):
        return False
    if year is None:
        return True
    start_date = media_item.get("startDate")
    start_date_payload = cast(dict[str, object], start_date) if isinstance(start_date, dict) else {}
    return start_date_payload.get("year") == year


def _title_matches(
    media_item: dict[str, object],
    title: str,
    *,
    allow_extended_variant: bool,
) -> bool:
    expected = _normalized_title(title)
    expected_tokens = _title_tokens(title)
    if not expected or not expected_tokens:
        return False
    for candidate in _candidate_titles(media_item):
        if _normalized_title(candidate) == expected:
            return True
        if _is_title_variant(
            candidate_title=candidate,
            expected_tokens=expected_tokens,
            allow_extended_variant=allow_extended_variant,
        ):
            return True
    return False


def _is_title_variant(
    *,
    candidate_title: str,
    expected_tokens: list[str],
    allow_extended_variant: bool,
) -> bool:
    candidate_tokens = _title_tokens(candidate_title)
    if len(candidate_tokens) <= len(expected_tokens):
        return False
    if candidate_tokens[: len(expected_tokens)] != expected_tokens:
        return False
    if candidate_tokens[len(expected_tokens)] in SEASON_VARIANT_MARKERS:
        return True
    return allow_extended_variant and len(expected_tokens) >= MIN_EXTENDED_VARIANT_TOKENS


def _candidate_titles(media_item: dict[str, object]) -> list[str]:
    candidates: list[str] = []
    raw_title = media_item.get("title")
    if isinstance(raw_title, dict):
        title_payload = cast(dict[str, object], raw_title)
        candidates.extend(value for value in title_payload.values() if isinstance(value, str))
    raw_synonyms = media_item.get("synonyms")
    if isinstance(raw_synonyms, list):
        synonym_values = cast(list[object], raw_synonyms)
        candidates.extend(value for value in synonym_values if isinstance(value, str))
    return candidates


def _normalized_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", title.casefold())


def _title_tokens(title: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", title.casefold())
