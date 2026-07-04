from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GeneratedFile, LibraryEntry, MediaItem, SyncRun
from app.library.paths import ensure_within_root
from app.sync.torbox_strm import SyncedStrmFile, TorBoxStrmSyncResult


class SyncStateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_success(self, result: TorBoxStrmSyncResult, library_root: Path) -> int:
        sync_run = SyncRun(
            status="success",
            scanned_count=result.scanned_files,
            written_count=result.written_files,
            skipped_count=result.skipped_files,
        )
        self._session.add(sync_run)
        await self._session.flush()

        for synced_file in result.synced_files:
            media_item = await self._media_item(synced_file)
            library_entry = await self._library_entry(media_item, synced_file)
            await self._generated_file(library_entry, synced_file, library_root)

        await self._session.commit()
        return sync_run.id

    async def _media_item(self, synced_file: SyncedStrmFile) -> MediaItem:
        result = await self._session.execute(
            select(MediaItem).where(
                MediaItem.media_type == synced_file.category,
                MediaItem.title == synced_file.title,
                MediaItem.year == synced_file.year,
            )
        )
        media_item = result.scalar_one_or_none()
        if media_item is not None:
            return media_item
        media_item = MediaItem(
            media_type=synced_file.category,
            title=synced_file.title,
            year=synced_file.year,
        )
        self._session.add(media_item)
        await self._session.flush()
        return media_item

    async def _library_entry(
        self,
        media_item: MediaItem,
        synced_file: SyncedStrmFile,
    ) -> LibraryEntry:
        result = await self._session.execute(
            select(LibraryEntry).where(LibraryEntry.opaque_id == synced_file.entry_id)
        )
        library_entry = result.scalar_one_or_none()
        if library_entry is None:
            library_entry = LibraryEntry(
                opaque_id=synced_file.entry_id,
                media_item_id=media_item.id,
                category=synced_file.category,
                season_number=synced_file.season_number,
                episode_number=synced_file.episode_number,
                provider=synced_file.provider,
                provider_item_id=synced_file.provider_item_id,
                provider_file_id=synced_file.provider_file_id,
            )
            self._session.add(library_entry)
            await self._session.flush()
            return library_entry

        library_entry.media_item_id = media_item.id
        library_entry.category = synced_file.category
        library_entry.season_number = synced_file.season_number
        library_entry.episode_number = synced_file.episode_number
        library_entry.provider = synced_file.provider
        library_entry.provider_item_id = synced_file.provider_item_id
        library_entry.provider_file_id = synced_file.provider_file_id
        return library_entry

    async def _generated_file(
        self,
        library_entry: LibraryEntry,
        synced_file: SyncedStrmFile,
        library_root: Path,
    ) -> None:
        relative_path = _relative_generated_path(library_root, synced_file.path)
        result = await self._session.execute(
            select(GeneratedFile).where(GeneratedFile.relative_path == relative_path)
        )
        generated_file = result.scalar_one_or_none()
        if generated_file is None:
            self._session.add(
                GeneratedFile(
                    library_entry_id=library_entry.id,
                    relative_path=relative_path,
                    content_hash=synced_file.content_hash,
                )
            )
            return

        generated_file.library_entry_id = library_entry.id
        generated_file.content_hash = synced_file.content_hash


def _relative_generated_path(library_root: Path, path: Path) -> str:
    safe_path = ensure_within_root(library_root, path)
    return safe_path.relative_to(library_root.resolve(strict=False)).as_posix()
