from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    GeneratedFile,
    LibraryEntry,
    MediaItem,
    TorBoxItem,
    TorBoxStoredFile,
    utc_now,
)
from app.db.repositories.media_identity import (
    MediaIdentityRepository,
    MediaIdentityWrite,
    SourceBindingWrite,
)
from app.db.repositories.sync_runs import (
    SyncErrorRecord,
    SyncRunRecord,
    SyncRunSource,
    SyncStatusSnapshot,
)
from app.domain.media_identity import (
    content_kind_for_category,
    parse_library_category,
    provider_kind_for_content,
)
from app.library.paths import ensure_within_root
from app.sync.torbox_strm import SyncedStrmFile, TorBoxStrmSyncResult


class SyncLibraryStateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def persist_result(
        self,
        result: TorBoxStrmSyncResult,
        library_root: Path,
        *,
        retained_info_hashes: frozenset[str] | None = None,
    ) -> None:
        identity_repository = MediaIdentityRepository(self._session)

        for synced_file in result.synced_files:
            media_item = await self._media_item(synced_file, identity_repository)
            torbox_file = await self._torbox_file(synced_file)
            library_entry = await self._library_entry(media_item, torbox_file, synced_file)
            await self._generated_file(library_entry, synced_file, library_root)

        if not result.partial:
            retained_info_hashes = retained_info_hashes or frozenset()
            await self._remove_stale_generated_files(
                result,
                library_root,
                retained_info_hashes,
            )
            await self._remove_stale_torbox_sources(result)

        _ = await identity_repository.delete_orphaned_media()

    async def retained_library_paths(
        self,
        library_root: Path,
        info_hashes: frozenset[str],
    ) -> set[Path]:
        if not info_hashes:
            return set()
        result = await self._session.execute(
            select(GeneratedFile.relative_path)
            .join(LibraryEntry)
            .where(LibraryEntry.info_hash.in_(info_hashes))
        )
        return {
            ensure_within_root(library_root, library_root / relative_path)
            for relative_path in result.scalars()
        }

    async def _media_item(
        self,
        synced_file: SyncedStrmFile,
        identity_repository: MediaIdentityRepository | None = None,
    ) -> MediaItem:
        repository = identity_repository or MediaIdentityRepository(self._session)
        content_kind = content_kind_for_category(synced_file.category)
        media_item = await repository.ensure_media(
            MediaIdentityWrite(
                content_kind=content_kind,
                library_category=parse_library_category(synced_file.category),
                title=synced_file.title,
                year=synced_file.year,
                tmdb_id=synced_file.tmdb_id,
                provider_media_kind=provider_kind_for_content(content_kind),
                authority=synced_file.identity_authority,
                confidence=synced_file.identity_confidence,
                resolver_version=synced_file.identity_resolver_version,
                poster_path=synced_file.tmdb_poster_path,
            )
        )
        await repository.bind_sources(
            media_item,
            SourceBindingWrite(
                source_kind=synced_file.provider,
                source_item_id=synced_file.provider_item_id,
                info_hash=synced_file.info_hash,
                source_title=synced_file.source_title or synced_file.title,
                authority=synced_file.identity_authority,
                confidence=synced_file.identity_confidence,
                resolver_version=synced_file.identity_resolver_version,
            ),
        )
        return media_item

    async def _library_entry(
        self,
        media_item: MediaItem,
        torbox_file: TorBoxStoredFile,
        synced_file: SyncedStrmFile,
    ) -> LibraryEntry:
        result = await self._session.execute(
            select(LibraryEntry).where(LibraryEntry.opaque_id == synced_file.entry_id)
        )
        library_entry = result.scalar_one_or_none()
        if library_entry is None and synced_file.info_hash is not None:
            result = await self._session.execute(
                select(LibraryEntry).where(
                    LibraryEntry.info_hash == synced_file.info_hash,
                    LibraryEntry.source_file_path == synced_file.provider_file_path,
                )
            )
            library_entry = result.scalar_one_or_none()
        if library_entry is None and synced_file.info_hash is not None:
            result = await self._session.execute(
                select(LibraryEntry).where(
                    LibraryEntry.info_hash == synced_file.info_hash,
                    LibraryEntry.source_file_name == synced_file.provider_file_name,
                    LibraryEntry.source_file_size == synced_file.provider_file_size,
                )
            )
            library_entry = result.scalar_one_or_none()
        if library_entry is None:
            library_entry = LibraryEntry(
                opaque_id=synced_file.entry_id,
                media_item_id=media_item.id,
                torbox_file_id=torbox_file.id,
                category=synced_file.category,
                season_number=synced_file.season_number,
                episode_number=synced_file.episode_number,
            )
            self._session.add(library_entry)
            await self._session.flush()
        library_entry.opaque_id = synced_file.entry_id
        library_entry.media_item_id = media_item.id
        library_entry.torbox_file_id = torbox_file.id
        library_entry.info_hash = synced_file.info_hash
        library_entry.source_kind = synced_file.provider
        library_entry.source_item_id = synced_file.provider_item_id
        library_entry.source_item_name = synced_file.provider_item_name
        library_entry.source_file_id = synced_file.provider_file_id
        library_entry.source_file_name = synced_file.provider_file_name
        library_entry.source_file_path = synced_file.provider_file_path
        library_entry.source_file_mime_type = synced_file.provider_file_mime_type
        library_entry.source_file_size = synced_file.provider_file_size
        library_entry.category = synced_file.category
        library_entry.season_number = synced_file.season_number
        library_entry.episode_number = synced_file.episode_number
        return library_entry

    async def _torbox_file(self, synced_file: SyncedStrmFile) -> TorBoxStoredFile:
        item_result = await self._session.execute(
            select(TorBoxItem).where(
                TorBoxItem.kind == synced_file.provider,
                TorBoxItem.external_id == synced_file.provider_item_id,
            )
        )
        torbox_item = item_result.scalar_one_or_none()
        if torbox_item is None:
            torbox_item = TorBoxItem(
                kind=synced_file.provider,
                external_id=synced_file.provider_item_id,
                name=synced_file.provider_item_name or synced_file.provider_item_id,
                raw_payload={},
            )
            self._session.add(torbox_item)
            await self._session.flush()
        else:
            torbox_item.name = synced_file.provider_item_name or torbox_item.name
            torbox_item.fetched_at = utc_now()

        file_result = await self._session.execute(
            select(TorBoxStoredFile).where(
                TorBoxStoredFile.torbox_item_id == torbox_item.id,
                TorBoxStoredFile.external_id == synced_file.provider_file_id,
            )
        )
        torbox_file = file_result.scalar_one_or_none()
        if torbox_file is None:
            torbox_file = TorBoxStoredFile(
                torbox_item_id=torbox_item.id,
                external_id=synced_file.provider_file_id,
                file_name=synced_file.provider_file_name,
                path=synced_file.provider_file_path,
                mime_type=synced_file.provider_file_mime_type,
                size=synced_file.provider_file_size,
            )
            self._session.add(torbox_file)
            await self._session.flush()
            return torbox_file
        torbox_file.file_name = synced_file.provider_file_name
        torbox_file.path = synced_file.provider_file_path
        torbox_file.mime_type = synced_file.provider_file_mime_type
        torbox_file.size = synced_file.provider_file_size
        return torbox_file

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

    async def _remove_stale_generated_files(
        self,
        result: TorBoxStrmSyncResult,
        library_root: Path,
        retained_info_hashes: frozenset[str],
    ) -> None:
        current_paths = {
            _relative_generated_path(library_root, synced_file.path)
            for synced_file in result.synced_files
        }
        retained_paths: set[str] = set()
        current_info_hashes = {
            synced_file.info_hash
            for synced_file in result.synced_files
            if synced_file.info_hash is not None
        }
        absent_info_hashes = retained_info_hashes - current_info_hashes
        if absent_info_hashes:
            retained_result = await self._session.execute(
                select(GeneratedFile.relative_path)
                .join(LibraryEntry)
                .where(LibraryEntry.info_hash.in_(absent_info_hashes))
            )
            retained_paths = set(retained_result.scalars())
        stale_result = await self._session.execute(select(GeneratedFile))
        for generated_file in stale_result.scalars():
            if (
                generated_file.relative_path in current_paths
                or generated_file.relative_path in retained_paths
            ):
                continue
            await self._session.delete(generated_file)

    async def _remove_stale_torbox_sources(self, result: TorBoxStrmSyncResult) -> None:
        current_sources = {
            (synced_file.provider, synced_file.provider_item_id, synced_file.provider_file_id)
            for synced_file in result.synced_files
        }
        source_result = await self._session.execute(
            select(TorBoxStoredFile, TorBoxItem).join(TorBoxItem)
        )
        for torbox_file, torbox_item in source_result.all():
            source = (torbox_item.kind, torbox_item.external_id, torbox_file.external_id)
            if source not in current_sources:
                await self._session.delete(torbox_file)
        current_items = {(kind, item_id) for kind, item_id, _ in current_sources}
        item_result = await self._session.execute(select(TorBoxItem))
        for torbox_item in item_result.scalars():
            if (torbox_item.kind, torbox_item.external_id) not in current_items:
                await self._session.delete(torbox_item)


def _relative_generated_path(library_root: Path, path: Path) -> str:
    safe_path = ensure_within_root(library_root, path)
    return safe_path.relative_to(library_root.resolve(strict=False)).as_posix()


__all__ = [
    "SyncErrorRecord",
    "SyncLibraryStateRepository",
    "SyncRunRecord",
    "SyncRunSource",
    "SyncStatusSnapshot",
]
