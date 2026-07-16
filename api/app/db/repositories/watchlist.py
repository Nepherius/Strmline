from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GeneratedFile, LibraryEntry, LibraryExclusion, MediaItem, WatchlistItem


@dataclass(frozen=True, slots=True)
class WatchlistItemWrite:
    tmdb_id: int
    imdb_id: str | None
    title: str
    year: str | None
    overview: str
    poster_url: str | None
    media_type: str = "series"


class WatchlistRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> tuple[WatchlistItem, ...]:
        result = await self._session.execute(
            select(WatchlistItem).order_by(func.lower(WatchlistItem.title))
        )
        return tuple(result.scalars())

    async def upsert(self, write: WatchlistItemWrite) -> WatchlistItem:
        item = await self._by_identity(write.media_type, write.tmdb_id)
        if item is None:
            item = WatchlistItem(tmdb_id=write.tmdb_id)
            self._session.add(item)

        item.imdb_id = write.imdb_id
        item.title = write.title
        item.year = write.year
        item.overview = write.overview
        item.poster_url = write.poster_url
        item.media_type = write.media_type
        await self._session.flush()
        return item

    async def library_contains(self, media_type: str, tmdb_id: int) -> bool:
        categories = ("movies",) if media_type == "movie" else ("shows", "anime")
        paths_result = await self._session.execute(
            select(GeneratedFile.relative_path)
            .join(LibraryEntry)
            .join(MediaItem)
            .where(
                MediaItem.tmdb_id == str(tmdb_id),
                LibraryEntry.category.in_(categories),
            )
        )
        paths = tuple(str(path) for path in paths_result.scalars())
        if not paths:
            return False
        exclusions_result = await self._session.execute(select(LibraryExclusion.relative_prefix))
        exclusions = tuple(str(prefix) for prefix in exclusions_result.scalars())
        return any(not _is_excluded(path, exclusions) for path in paths)

    async def delete_identities(self, identities: set[tuple[str, int]]) -> int:
        deleted = 0
        for media_type in ("movie", "series"):
            tmdb_ids = {
                tmdb_id for identity_type, tmdb_id in identities if identity_type == media_type
            }
            if not tmdb_ids:
                continue
            result = await self._session.execute(
                delete(WatchlistItem)
                .where(
                    WatchlistItem.media_type == media_type,
                    WatchlistItem.tmdb_id.in_(tmdb_ids),
                )
                .returning(WatchlistItem.id)
            )
            deleted += len(tuple(result.scalars()))
        return deleted

    async def delete(self, media_type: str, tmdb_id: int) -> bool:
        item = await self._by_identity(media_type, tmdb_id)
        if item is None:
            return False
        await self._session.delete(item)
        await self._session.flush()
        return True

    async def _by_identity(self, media_type: str, tmdb_id: int) -> WatchlistItem | None:
        result = await self._session.execute(
            select(WatchlistItem).where(
                WatchlistItem.media_type == media_type,
                WatchlistItem.tmdb_id == tmdb_id,
            )
        )
        return result.scalar_one_or_none()


def _is_excluded(relative_path: str, exclusions: tuple[str, ...]) -> bool:
    return any(
        relative_path == prefix or relative_path.startswith(f"{prefix}/") for prefix in exclusions
    )
