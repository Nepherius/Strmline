from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LibraryEntry, StreamSelection


@dataclass(frozen=True, slots=True)
class StreamSelectionWrite:
    stream_key: str
    media_type: str
    media_id: str
    title: str
    source_name: str | None
    info_hash: str | None
    torbox_torrent_id: str | None
    tmdb_id: str | None = None
    media_title: str | None = None
    media_year: int | None = None
    media_poster_path: str | None = None
    status: str = "selected"


@dataclass(frozen=True, slots=True)
class StreamSelectionRecord:
    stream_key: str
    media_type: str
    media_id: str
    title: str
    source_name: str | None
    info_hash: str | None
    torbox_torrent_id: str | None
    status: str
    tmdb_id: str | None = None
    media_title: str | None = None
    media_year: int | None = None
    media_poster_path: str | None = None


class StreamSelectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def selected_keys(self, stream_keys: list[str]) -> set[str]:
        if not stream_keys:
            return set()
        result = await self._session.execute(
            select(StreamSelection.stream_key).where(StreamSelection.stream_key.in_(stream_keys))
        )
        return set(result.scalars())

    async def get(self, stream_key: str) -> StreamSelectionRecord | None:
        selection = await self._selection(stream_key)
        return _record(selection) if selection is not None else None

    async def list_selected(self) -> tuple[StreamSelectionRecord, ...]:
        result = await self._session.execute(
            select(StreamSelection).where(StreamSelection.status == "selected")
        )
        return tuple(_record(selection) for selection in result.scalars())

    async def upsert(self, write: StreamSelectionWrite) -> StreamSelectionRecord:
        selection = await self._selection(write.stream_key)
        if selection is None:
            selection = StreamSelection(
                stream_key=write.stream_key,
                media_type=write.media_type,
                media_id=write.media_id,
                tmdb_id=write.tmdb_id,
                media_title=write.media_title,
                media_year=write.media_year,
                media_poster_path=write.media_poster_path,
                title=write.title,
                source_name=write.source_name,
                info_hash=write.info_hash,
                torbox_torrent_id=write.torbox_torrent_id,
                status=write.status,
            )
            self._session.add(selection)
            await self._session.flush()
            return _record(selection)

        selection.media_type = write.media_type
        selection.media_id = write.media_id
        selection.tmdb_id = write.tmdb_id
        selection.media_title = write.media_title
        selection.media_year = write.media_year
        selection.media_poster_path = write.media_poster_path
        selection.title = write.title
        selection.source_name = write.source_name
        selection.info_hash = write.info_hash
        selection.torbox_torrent_id = write.torbox_torrent_id
        selection.status = write.status
        await self._session.flush()
        return _record(selection)

    async def update_torbox_id(self, stream_key: str, torbox_torrent_id: str | None) -> None:
        selection = await self._selection(stream_key)
        if selection is not None:
            selection.torbox_torrent_id = torbox_torrent_id
            await self._session.flush()

    async def update_media_identity(
        self,
        stream_key: str,
        *,
        tmdb_id: str,
        media_title: str,
        media_year: int | None,
        media_poster_path: str | None,
    ) -> None:
        selection = await self._selection(stream_key)
        if selection is None:
            return
        selection.tmdb_id = tmdb_id
        selection.media_title = media_title
        selection.media_year = media_year
        selection.media_poster_path = media_poster_path
        await self._session.flush()

    async def delete(self, stream_key: str) -> bool:
        selection = await self._selection(stream_key)
        if selection is None:
            return False
        if selection.info_hash is not None:
            _ = await self._session.execute(
                update(LibraryEntry)
                .where(LibraryEntry.info_hash == selection.info_hash.casefold())
                .values(info_hash=None)
            )
        await self._session.delete(selection)
        await self._session.flush()
        return True

    async def _selection(self, stream_key: str) -> StreamSelection | None:
        result = await self._session.execute(
            select(StreamSelection).where(StreamSelection.stream_key == stream_key)
        )
        return result.scalar_one_or_none()


def _record(selection: StreamSelection) -> StreamSelectionRecord:
    return StreamSelectionRecord(
        stream_key=selection.stream_key,
        media_type=selection.media_type,
        media_id=selection.media_id,
        title=selection.title,
        source_name=selection.source_name,
        info_hash=selection.info_hash,
        torbox_torrent_id=selection.torbox_torrent_id,
        status=selection.status,
        tmdb_id=selection.tmdb_id,
        media_title=selection.media_title,
        media_year=selection.media_year,
        media_poster_path=selection.media_poster_path,
    )
