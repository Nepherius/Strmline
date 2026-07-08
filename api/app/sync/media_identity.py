from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any, cast

from app.providers.tmdb.cache_keys import tmdb_cache_key
from app.providers.tmdb.metadata import TmdbMetadataService

logger = logging.getLogger(__name__)

MIN_MATCH_SCORE = 0.4
MIN_DATE_LENGTH = 4


@dataclass(frozen=True, slots=True)
class MediaIdentity:
    tmdb_id: str | None
    title: str
    year: int | None
    media_type: str


class MediaIdentityResolver:
    def __init__(
        self,
        metadata_service: TmdbMetadataService | None,
        *,
        delay_seconds: float = 0.25,
    ) -> None:
        self._metadata_service = metadata_service
        self._delay_seconds = delay_seconds
        self._memory_cache: dict[tuple[str, int | None, str], MediaIdentity] = {}
        self._semaphore = asyncio.Semaphore(1)

    async def resolve(
        self,
        parsed_title: str,
        year: int | None,
        category: str,
    ) -> MediaIdentity:
        cache_key = (parsed_title, year, category)
        if cache_key in self._memory_cache:
            return self._memory_cache[cache_key]

        query_media_type = "movie" if category == "movies" else "tv"
        fallback = MediaIdentity(
            tmdb_id=None,
            title=parsed_title,
            year=year,
            media_type=query_media_type,
        )

        if not self._metadata_service:
            return fallback

        try:
            identity = await self._do_resolve(parsed_title, year, query_media_type)
        except Exception as error:  # noqa: BLE001
            logger.warning("Failed to resolve TMDB identity for '%s': %s", parsed_title, error)
            return fallback
        else:
            self._memory_cache[cache_key] = identity
            return identity

    async def _do_resolve(
        self,
        parsed_title: str,
        year: int | None,
        query_media_type: str,
    ) -> MediaIdentity:
        service = self._metadata_service
        if service is None:
            return MediaIdentity(
                tmdb_id=None,
                title=parsed_title,
                year=year,
                media_type=query_media_type,
            )

        endpoint = "/search/multi"
        params = {"query": parsed_title, "include_adult": "false"}
        db_key = tmdb_cache_key(endpoint, params)

        # Check DB cache first
        cached_val = await service._cache_repository.get_fresh(db_key)  # pyright: ignore[reportPrivateUsage]
        if cached_val is not None:
            payload = cached_val.response_payload
        else:
            # Cache miss: rate limit
            async with self._semaphore:
                await asyncio.sleep(self._delay_seconds)
                payload = await service.get_json(endpoint, params=params)

        results = payload.get("results")
        if not isinstance(results, list) or not results:
            return MediaIdentity(
                tmdb_id=None,
                title=parsed_title,
                year=year,
                media_type=query_media_type,
            )

        results_list = results
        valid_results: list[dict[str, Any]] = [
            cast("dict[str, Any]", r) for r in results_list if isinstance(r, dict)
        ]
        scored_candidates = self._score_results(valid_results, parsed_title, year, query_media_type)

        if not scored_candidates:
            return MediaIdentity(
                tmdb_id=None,
                title=parsed_title,
                year=year,
                media_type=query_media_type,
            )

        # Pick candidate with highest score
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        return scored_candidates[0][1]

    def _score_results(
        self,
        results: list[dict[str, Any]],
        parsed_title: str,
        year: int | None,
        query_media_type: str,
    ) -> list[tuple[float, MediaIdentity]]:
        scored_candidates: list[tuple[float, MediaIdentity]] = []
        for raw in results:
            tmdb_id = raw.get("id")
            if tmdb_id is None:
                continue

            raw_media_type = raw.get("media_type")
            if raw_media_type not in ("movie", "tv"):
                continue

            if raw_media_type == "movie":
                res_title = raw.get("title") or raw.get("original_title")
                date_str = raw.get("release_date")
            else:
                res_title = raw.get("name") or raw.get("original_name")
                date_str = raw.get("first_air_date")

            if not isinstance(res_title, str) or not res_title:
                continue

            res_year = parse_year(date_str)
            score = score_match(
                query_title=parsed_title,
                query_year=year,
                query_media_type=query_media_type,
                result_title=res_title,
                result_year=res_year,
                result_media_type=str(raw_media_type),
            )

            if score >= MIN_MATCH_SCORE:
                scored_candidates.append(
                    (
                        score,
                        MediaIdentity(
                            tmdb_id=str(tmdb_id),
                            title=res_title,
                            year=res_year,
                            media_type=str(raw_media_type),
                        ),
                    )
                )
        return scored_candidates


def parse_year(date_str: object) -> int | None:
    if not isinstance(date_str, str) or len(date_str) < MIN_DATE_LENGTH:
        return None
    try:
        return int(date_str[:MIN_DATE_LENGTH])
    except ValueError:
        return None


def normalize_title(text: str) -> str:
    text = text.replace("'", "").replace("\u2019", "")
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return " ".join(cleaned.split())


def title_similarity(t1: str, t2: str) -> float:
    n1 = normalize_title(t1)
    n2 = normalize_title(t2)
    if n1 == n2:
        return 1.0
    s1 = set(n1.split())
    s2 = set(n2.split())
    if not s1 or not s2:
        return 0.0
    intersection = s1.intersection(s2)
    union = s1.union(s2)
    return len(intersection) / len(union)


def score_match(
    query_title: str,
    query_year: int | None,
    query_media_type: str,
    result_title: str,
    result_year: int | None,
    result_media_type: str,
) -> float:
    if query_media_type != result_media_type:
        return 0.0

    similarity = title_similarity(query_title, result_title)

    if query_year is not None and result_year is not None:
        year_diff = abs(query_year - result_year)
        if year_diff == 0:
            year_score = 1.0
        elif year_diff == 1:
            year_score = 0.5
        else:
            return 0.0
    else:
        year_score = 0.8

    return similarity * year_score
