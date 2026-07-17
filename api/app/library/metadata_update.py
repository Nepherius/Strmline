from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.library.metadata_refresh import refresh_library_metadata
from app.providers.tmdb.client import TmdbClient
from app.providers.tmdb.posters import TmdbPosterClient


async def refresh_tmdb_metadata(
    session: AsyncSession,
    settings: Settings,
    *,
    library_root: Path,
    media_item_id: int,
    tmdb_api_key: str,
) -> int:
    """Refresh one media aggregate from its exact persisted TMDB identity."""
    return await refresh_library_metadata(
        session,
        library_root=library_root,
        media_item_id=media_item_id,
        tmdb_client=TmdbClient(
            api_key=tmdb_api_key,
            base_url=settings.tmdb_base_url,
            timeout_seconds=settings.outbound_timeout_seconds,
        ),
        poster_fetcher=TmdbPosterClient(timeout_seconds=settings.outbound_timeout_seconds),
    )
