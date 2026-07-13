from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    GeneratedFile,
    LibraryEntry,
    MediaItem,
    SyncError,
    SyncRun,
    TorBoxItem,
    TorBoxStoredFile,
    utc_now,
)
from app.library.paths import ensure_within_root
from app.sync.torbox_strm import SyncedStrmFile, TorBoxStrmSyncResult

SyncRunSource = Literal["manual", "auto", "season_auto_complete"]


@dataclass(frozen=True, slots=True)
class SyncRunRecord:
    id: int
    status: str
    source: str
    started_at: datetime
    finished_at: datetime | None
    scanned_count: int
    written_count: int
    skipped_count: int


@dataclass(frozen=True, slots=True)
class SyncErrorRecord:
    id: int
    sync_run_id: int
    phase: str
    item_ref: str | None
    message: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SyncStatusSnapshot:
    last_run: SyncRunRecord | None
    last_auto_run: SyncRunRecord | None
    recent_errors: tuple[SyncErrorRecord, ...]


class SyncStateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_success(
        self,
        result: TorBoxStrmSyncResult,
        library_root: Path,
        *,
        source: SyncRunSource = "manual",
    ) -> int:
        started_at = utc_now()
        sync_run = SyncRun(
            status="success",
            source=source,
            started_at=started_at,
            finished_at=utc_now(),
            scanned_count=result.scanned_files,
            written_count=result.written_files,
            skipped_count=result.skipped_files,
        )
        self._session.add(sync_run)
        await self._session.flush()

        for synced_file in result.synced_files:
            media_item = await self._media_item(synced_file)
            torbox_file = await self._torbox_file(synced_file)
            library_entry = await self._library_entry(media_item, torbox_file, synced_file)
            await self._generated_file(library_entry, synced_file, library_root)

        if not result.partial:
            await self._remove_stale_generated_files(result, library_root)
            await self._remove_stale_torbox_sources(result)

        await self._session.commit()
        return sync_run.id

    async def record_failure(  # noqa: PLR0913
        self,
        *,
        phase: str,
        message: str,
        source: SyncRunSource = "manual",
        item_ref: str | None = None,
        scanned_count: int = 0,
        written_count: int = 0,
        skipped_count: int = 0,
    ) -> int:
        started_at = utc_now()
        sync_run = SyncRun(
            status="failed",
            source=source,
            started_at=started_at,
            finished_at=utc_now(),
            scanned_count=scanned_count,
            written_count=written_count,
            skipped_count=skipped_count,
        )
        self._session.add(sync_run)
        await self._session.flush()
        self._session.add(
            SyncError(
                sync_run_id=sync_run.id,
                phase=phase,
                item_ref=item_ref,
                message=message,
            )
        )
        await self._session.commit()
        return sync_run.id

    async def record_season_completion(
        self,
        *,
        checked_shows: int,
        missing_episodes: int,
        added_torrents: int,
        diagnostics: tuple[tuple[str | None, str], ...],
    ) -> int:
        started_at = utc_now()
        sync_run = SyncRun(
            status="partial" if diagnostics else "success",
            source="season_auto_complete",
            started_at=started_at,
            finished_at=utc_now(),
            scanned_count=checked_shows,
            written_count=added_torrents,
            skipped_count=missing_episodes,
        )
        self._session.add(sync_run)
        await self._session.flush()
        self._session.add_all(
            [
                SyncError(
                    sync_run_id=sync_run.id,
                    phase="season_auto_complete",
                    item_ref=item_ref,
                    message=message,
                )
                for item_ref, message in diagnostics
            ]
        )
        await self._session.commit()
        return sync_run.id

    async def status(self, *, error_limit: int = 5) -> SyncStatusSnapshot:
        last_run_result = await self._session.execute(
            select(SyncRun)
            .where(SyncRun.source.in_(("manual", "auto")))
            .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
            .limit(1)
        )
        last_auto_run_result = await self._session.execute(
            select(SyncRun)
            .where(SyncRun.source == "auto")
            .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
            .limit(1)
        )
        errors_result = await self._session.execute(
            select(SyncError)
            .where(SyncError.dismissed_at.is_(None))
            .order_by(SyncError.created_at.desc(), SyncError.id.desc())
            .limit(error_limit)
        )
        last_run = last_run_result.scalar_one_or_none()
        last_auto_run = last_auto_run_result.scalar_one_or_none()
        return SyncStatusSnapshot(
            last_run=_sync_run_record(last_run) if last_run is not None else None,
            last_auto_run=(_sync_run_record(last_auto_run) if last_auto_run is not None else None),
            recent_errors=tuple(_sync_error_record(error) for error in errors_result.scalars()),
        )

    async def dismiss_error(self, error_id: int) -> bool:
        result = await self._session.execute(select(SyncError).where(SyncError.id == error_id))
        sync_error = result.scalar_one_or_none()
        if sync_error is None:
            return False
        if sync_error.dismissed_at is None:
            sync_error.dismissed_at = utc_now()
            await self._session.commit()
        return True

    async def _media_item(self, synced_file: SyncedStrmFile) -> MediaItem:
        # Try TMDB ID match first
        if synced_file.tmdb_id is not None:
            result = await self._session.execute(
                select(MediaItem).where(MediaItem.tmdb_id == synced_file.tmdb_id)
            )
            media_item = result.scalar_one_or_none()
            if media_item is not None:
                media_item.media_type = synced_file.category
                media_item.title = synced_file.title
                media_item.year = synced_file.year
                return media_item

        # Fall back to title+year matching
        result = await self._session.execute(
            select(MediaItem).where(
                MediaItem.media_type == synced_file.category,
                MediaItem.title == synced_file.title,
                (MediaItem.year == synced_file.year)
                | (MediaItem.year.is_(None))
                | (synced_file.year is None),
            )
        )
        media_item = result.scalar_one_or_none()
        if media_item is not None:
            if synced_file.tmdb_id is not None:
                media_item.tmdb_id = synced_file.tmdb_id
            if media_item.year is None and synced_file.year is not None:
                media_item.year = synced_file.year
            return media_item

        media_item = MediaItem(
            media_type=synced_file.category,
            title=synced_file.title,
            year=synced_file.year,
            tmdb_id=synced_file.tmdb_id,
        )
        self._session.add(media_item)
        await self._session.flush()
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
            return library_entry

        library_entry.media_item_id = media_item.id
        library_entry.torbox_file_id = torbox_file.id
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
    ) -> None:
        current_paths = {
            _relative_generated_path(library_root, synced_file.path)
            for synced_file in result.synced_files
        }
        stale_result = await self._session.execute(select(GeneratedFile))
        for generated_file in stale_result.scalars():
            if generated_file.relative_path in current_paths:
                continue
            stale_path = ensure_within_root(
                library_root, library_root / generated_file.relative_path
            )
            if stale_path.suffix == ".strm" and stale_path.exists():
                stale_path.unlink()
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


def _sync_run_record(sync_run: SyncRun) -> SyncRunRecord:
    return SyncRunRecord(
        id=sync_run.id,
        status=sync_run.status,
        source=sync_run.source,
        started_at=sync_run.started_at,
        finished_at=sync_run.finished_at,
        scanned_count=sync_run.scanned_count,
        written_count=sync_run.written_count,
        skipped_count=sync_run.skipped_count,
    )


def _sync_error_record(error: SyncError) -> SyncErrorRecord:
    return SyncErrorRecord(
        id=error.id,
        sync_run_id=error.sync_run_id,
        phase=error.phase,
        item_ref=error.item_ref,
        message=error.message,
        created_at=error.created_at,
    )
