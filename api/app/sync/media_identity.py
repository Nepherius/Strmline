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
MIN_LATIN_LENGTH = 3
MIN_CJK_LENGTH = 2
MAX_POSTER_PATH_LENGTH = 300

JUNK_PREFIXES = re.compile(
    r"(?i)^(?:\bwww\b.*\bcom\b|\bwww\b.*\borg\b|\bwww\b\s*|\b\d*tamilmv\b|\bcards\b|\bcenter\b|\b TamilMV\b|\b\d*tamilultra\b|\bmasstamilan\b|\bisaimini\b|\btamilyogi\b|\btamilrockers\b|\bcenter\s*|\[[^\]]+\]|\b(?:YIFY|YTS|RARBG|EZTV|ETTV|KAT|LimeTorrents|Demonoid|Scene|Tamilrockers|Tamilmv|Isaimini|Tamilyogi|Movierulz|Tamilgun|1337x|Worldfree4u|Madrasrockers|Thiruttumovies|Hiidude|Mymoviesda|Filmlinks4u|Tamildbox|Tamilrage|Mtamilrockers)\b|\b(?:www|https?://)\S+|\b(?:com|org|net|in|co\.uk|io)\b|\b(?:movies|films|download|free|watch|online)\b|[\s._-])+"
)


@dataclass(frozen=True, slots=True)
class MediaIdentity:
    tmdb_id: str | None
    title: str
    year: int | None
    media_type: str
    poster_path: str | None = None


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
            title=_fallback_title(parsed_title),
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

        queries = extract_search_queries(parsed_title)

        for query in queries:
            endpoint = "/search/multi"
            params = {"query": query, "include_adult": "false"}
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
                continue

            results_list = cast(list[Any], results)
            valid_results: list[dict[str, Any]] = [
                cast("dict[str, Any]", r) for r in results_list if isinstance(r, dict)
            ]
            scored_candidates = self._score_results(
                valid_results, parsed_title, query, year, query_media_type
            )

            if scored_candidates:
                scored_candidates.sort(key=lambda x: x[0], reverse=True)
                return scored_candidates[0][1]
            unique_same_year = _unique_same_year_identity(
                valid_results,
                query_media_type=query_media_type,
                year=year,
            )
            if unique_same_year is not None:
                return unique_same_year

        return MediaIdentity(
            tmdb_id=None,
            title=_fallback_title(parsed_title),
            year=year,
            media_type=query_media_type,
        )

    def _score_results(
        self,
        results: list[dict[str, Any]],
        parsed_title: str,
        search_query: str,
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

            if search_query != parsed_title:
                clean_score = score_match(
                    query_title=search_query,
                    query_year=year,
                    query_media_type=query_media_type,
                    result_title=res_title,
                    result_year=res_year,
                    result_media_type=str(raw_media_type),
                )
                score = max(score, clean_score)

            if score >= MIN_MATCH_SCORE:
                scored_candidates.append(
                    (
                        score,
                        MediaIdentity(
                            tmdb_id=str(tmdb_id),
                            title=res_title,
                            year=res_year,
                            media_type=str(raw_media_type),
                            poster_path=_poster_path(raw),
                        ),
                    )
                )
        return scored_candidates


def _unique_same_year_identity(
    results: list[dict[str, Any]],
    *,
    query_media_type: str,
    year: int | None,
) -> MediaIdentity | None:
    if year is None:
        return None
    candidates: list[MediaIdentity] = []
    for raw in results:
        identity = _result_identity(raw)
        if identity is None or identity.media_type != query_media_type:
            continue
        if identity.year == year:
            candidates.append(identity)
    return candidates[0] if len(candidates) == 1 else None


def _result_identity(raw: dict[str, Any]) -> MediaIdentity | None:
    tmdb_id = raw.get("id")
    media_type = raw.get("media_type")
    if tmdb_id is None or media_type not in ("movie", "tv"):
        return None
    if media_type == "movie":
        title = raw.get("title") or raw.get("original_title")
        year = parse_year(raw.get("release_date"))
    else:
        title = raw.get("name") or raw.get("original_name")
        year = parse_year(raw.get("first_air_date"))
    if not isinstance(title, str) or not title:
        return None
    return MediaIdentity(
        tmdb_id=str(tmdb_id),
        title=title,
        year=year,
        media_type=str(media_type),
        poster_path=_poster_path(raw),
    )


def _poster_path(raw: dict[str, Any]) -> str | None:
    poster_path = raw.get("poster_path")
    if not isinstance(poster_path, str) or not poster_path.startswith("/"):
        return None
    return poster_path if len(poster_path) <= MAX_POSTER_PATH_LENGTH else None


def clean_search_title(title: str) -> str:
    cleaned = JUNK_PREFIXES.sub("", title).strip()
    if not cleaned:
        return title
    return cleaned


def _fallback_title(title: str) -> str:
    queries = extract_search_queries(title)
    cleaned = queries[0]
    if len(queries) > 1 and _contains_cjk(cleaned):
        cleaned = queries[1]
    if cleaned.isupper() and any(character.isalpha() for character in cleaned):
        return cleaned.title()
    return cleaned


def extract_search_queries(title: str) -> list[str]:
    cleaned = clean_search_title(title)
    queries = [cleaned]

    # Check for CJK + Latin mix
    cjk_pattern = re.compile(r"[\u3040-\u30ff\u4e00-\u9faf\uac00-\ud7af]+")
    has_cjk = _contains_cjk(cleaned)

    latin_pattern = re.compile(r"[a-zA-Z]{3,}")
    has_latin = bool(latin_pattern.search(cleaned))

    if has_cjk and has_latin:
        # Extract Latin part
        latin_parts = " ".join(re.findall(r"[a-zA-Z0-9']{2,}", cleaned))
        if latin_parts and len(latin_parts) >= MIN_LATIN_LENGTH:
            queries.append(latin_parts)

        # Extract CJK part
        cjk_parts = " ".join(cjk_pattern.findall(cleaned))
        if cjk_parts and len(cjk_parts) >= MIN_CJK_LENGTH:
            queries.append(cjk_parts)

    return queries


def _contains_cjk(value: str) -> bool:
    return bool(re.search(r"[\u3040-\u30ff\u4e00-\u9faf\uac00-\ud7af]", value))


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
