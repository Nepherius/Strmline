from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import WatchlistItem


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
        item = await self._by_tmdb_id(write.tmdb_id)
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

    async def delete(self, tmdb_id: int) -> bool:
        item = await self._by_tmdb_id(tmdb_id)
        if item is None:
            return False
        await self._session.delete(item)
        await self._session.flush()
        return True

    async def _by_tmdb_id(self, tmdb_id: int) -> WatchlistItem | None:
        result = await self._session.execute(
            select(WatchlistItem).where(WatchlistItem.tmdb_id == tmdb_id)
        )
        return result.scalar_one_or_none()
