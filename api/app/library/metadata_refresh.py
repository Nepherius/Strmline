from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MediaItem
from app.db.repositories.media_metadata import MediaMetadataRepository
from app.db.repositories.tmdb_cache import TmdbCacheRepository
from app.library.posters import PosterFetcher, refresh_posters
from app.providers.tmdb.cache_keys import tmdb_cache_key
from app.providers.tmdb.client import TmdbClient

METADATA_REFRESH_TTL = timedelta(days=365)
YEAR_LENGTH = 4


class MetadataRefreshError(RuntimeError):
    """Raised when a library entry cannot be refreshed from its TMDB identity."""


async def refresh_library_metadata(
    session: AsyncSession,
    *,
    library_root: Path,
    media_item_id: int,
    tmdb_client: TmdbClient,
    poster_fetcher: PosterFetcher,
    require_poster: bool = True,
) -> int:
    record = await MediaMetadataRepository(session).find_for_media_item(media_item_id)
    if record is None:
        raise MetadataRefreshError("Library entry has no unique media record.")
    if record.tmdb_id is None or not record.tmdb_id.isdecimal():
        raise MetadataRefreshError("Library entry has no TMDB identity to refresh.")

    endpoint = _tmdb_endpoint(record.media_item.content_kind, record.tmdb_id)
    payload = await tmdb_client.get_json(endpoint)
    _apply_metadata(record.media_item, payload)
    await TmdbCacheRepository(session).store(
        cache_key=tmdb_cache_key(endpoint),
        endpoint=endpoint,
        request_params={},
        response_payload=payload,
        ttl=METADATA_REFRESH_TTL,
    )
    poster_path = payload.get("poster_path")
    if not isinstance(poster_path, str) or not poster_path:
        if require_poster:
            raise MetadataRefreshError("TMDB returned no poster for this library entry.")
        return 0
    return await refresh_posters(
        library_root,
        poster_fetcher,
        poster_path,
        record.tmdb_id,
    )


def _tmdb_endpoint(content_kind: str, tmdb_id: str) -> str:
    provider_type = "movie" if content_kind == "movie" else "tv"
    return f"/{provider_type}/{tmdb_id}"


def _apply_metadata(media_item: MediaItem, payload: dict[str, Any]) -> None:
    title = payload.get("title") if media_item.content_kind == "movie" else payload.get("name")
    if isinstance(title, str) and title.strip():
        media_item.title = title
    date_value = (
        payload.get("release_date")
        if media_item.content_kind == "movie"
        else payload.get("first_air_date")
    )
    if (
        isinstance(date_value, str)
        and len(date_value) >= YEAR_LENGTH
        and date_value[:YEAR_LENGTH].isdecimal()
    ):
        media_item.year = int(date_value[:YEAR_LENGTH])
    poster_path = payload.get("poster_path")
    if isinstance(poster_path, str) and poster_path:
        media_item.poster_path = poster_path
