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
    relative_prefix: str,
    tmdb_client: TmdbClient,
    poster_fetcher: PosterFetcher,
) -> int:
    record = await MediaMetadataRepository(session).find_for_library_prefix(relative_prefix)
    if record is None:
        raise MetadataRefreshError("Library entry has no unique media record.")
    if record.media_item.tmdb_id is None or not record.media_item.tmdb_id.isdecimal():
        raise MetadataRefreshError("Library entry has no TMDB identity to refresh.")

    endpoint = _tmdb_endpoint(record.media_item.media_type, record.media_item.tmdb_id)
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
        raise MetadataRefreshError("TMDB returned no poster for this library entry.")
    refreshed = await refresh_posters(
        library_root,
        poster_fetcher,
        poster_path,
        record.media_item.tmdb_id,
    )
    await session.commit()
    return refreshed


def _tmdb_endpoint(media_type: str, tmdb_id: str) -> str:
    provider_type = "movie" if media_type == "movies" else "tv"
    return f"/{provider_type}/{tmdb_id}"


def _apply_metadata(media_item: MediaItem, payload: dict[str, Any]) -> None:
    title = payload.get("title") if media_item.media_type == "movies" else payload.get("name")
    if isinstance(title, str) and title.strip():
        media_item.title = title
    date_value = (
        payload.get("release_date")
        if media_item.media_type == "movies"
        else payload.get("first_air_date")
    )
    if (
        isinstance(date_value, str)
        and len(date_value) >= YEAR_LENGTH
        and date_value[:YEAR_LENGTH].isdecimal()
    ):
        media_item.year = int(date_value[:YEAR_LENGTH])
