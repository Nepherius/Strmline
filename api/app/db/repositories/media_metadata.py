from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GeneratedFile, LibraryEntry, MediaItem

ENTRY_PATH_PARTS = 2


@dataclass(frozen=True, slots=True)
class LibraryMediaRecord:
    media_item: MediaItem


class MediaMetadataRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_for_library_prefix(self, relative_prefix: str) -> LibraryMediaRecord | None:
        result = await self._session.execute(
            select(MediaItem, GeneratedFile.relative_path)
            .select_from(GeneratedFile)
            .join(LibraryEntry)
            .join(MediaItem)
            .where(
                or_(
                    GeneratedFile.relative_path == relative_prefix,
                    GeneratedFile.relative_path.like(f"{relative_prefix}/%"),
                )
            )
        )
        records: dict[int, MediaItem] = {}
        for media_item, _generated_path in result.all():
            records[media_item.id] = media_item
        if len(records) != 1:
            return None
        return LibraryMediaRecord(media_item=next(iter(records.values())))

    async def tmdb_ids_for_library_prefixes(
        self,
        relative_prefixes: set[str],
    ) -> dict[str, str]:
        if not relative_prefixes:
            return {}
        result = await self._session.execute(
            select(GeneratedFile.relative_path, MediaItem.tmdb_id)
            .select_from(GeneratedFile)
            .join(LibraryEntry)
            .join(MediaItem)
            .where(MediaItem.tmdb_id.is_not(None))
        )
        tmdb_ids: dict[str, str] = {}
        for generated_path, tmdb_id in result.all():
            relative = Path(generated_path)
            if len(relative.parts) < ENTRY_PATH_PARTS or not isinstance(tmdb_id, str):
                continue
            prefix = "/".join(relative.parts[:ENTRY_PATH_PARTS])
            if prefix in relative_prefixes:
                tmdb_ids[prefix] = tmdb_id
        return tmdb_ids
