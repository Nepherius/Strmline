from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.repositories.classification_override import ClassificationOverrideRepository
from app.db.repositories.library_exclusion import LibraryExclusionRepository
from app.db.repositories.settings import AppSettingsRepository, SettingsSnapshot
from app.db.repositories.stream_selection import StreamSelectionRepository
from app.db.repositories.sync_coordination import SyncCoordinationRepository
from app.db.repositories.sync_runs import SyncRunRepository
from app.db.repositories.sync_state import SyncLibraryStateRepository
from app.db.repositories.tmdb_cache import TmdbCacheRepository
from app.library.mutation_journal import LibraryMutationJournal
from app.library.posters import cache_missing_posters
from app.providers.tmdb.client import TmdbClient
from app.providers.tmdb.metadata import TmdbMetadataService
from app.providers.tmdb.posters import TmdbPosterClient
from app.providers.torbox.client import TorBoxClient
from app.providers.torbox.files import DownloadKind, torrent_info_hash
from app.sync.anime_classification import build_anilist_anime_classifier
from app.sync.identity_inputs import IdentityInputs, selected_media_identities
from app.sync.media_identity import MediaIdentityResolver
from app.sync.service import (
    SyncAlreadyRunningError,
    SyncConfigurationError,
    SyncExecutionError,
    SyncRunSummary,
)
from app.sync.torbox_strm import (
    ResolverUrlConfig,
    SyncedStrmFile,
    TorBoxStrmSync,
    TorBoxStrmSyncResult,
)

logger = logging.getLogger(__name__)


class TorBoxClientFactory(Protocol):
    def __call__(self, *, api_key: str, base_url: str, timeout: float) -> TorBoxClient: ...


@dataclass(frozen=True, slots=True)
class _SingleTorrentClient:
    item: dict[str, Any]

    async def list_downloads(
        self,
        kind: DownloadKind,
        *,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        _ = limit
        return [self.item] if kind == "torrents" else []


async def run_torbox_item_sync(
    session: AsyncSession,
    settings: Settings,
    *,
    torrent_id: str,
    client_factory: TorBoxClientFactory = TorBoxClient,
) -> SyncRunSummary:
    """Upsert one confirmed TorBox torrent without global stale reconciliation."""
    coordination = SyncCoordinationRepository(session)
    if not await coordination.try_lock():
        raise SyncAlreadyRunningError("A sync run is already in progress.")
    try:
        return await _execute_item_sync(
            session,
            settings,
            torrent_id=torrent_id,
            client_factory=client_factory,
        )
    finally:
        await coordination.release()


async def _execute_item_sync(
    session: AsyncSession,
    settings: Settings,
    *,
    torrent_id: str,
    client_factory: TorBoxClientFactory,
) -> SyncRunSummary:
    sync_runs = SyncRunRepository(session)
    settings_repository = AppSettingsRepository(session, settings)
    snapshot = await settings_repository.snapshot_with_env()
    try:
        api_key = _required(await settings_repository.provider_api_key("torbox"), "TorBox API key")
        library_root = Path(_required(snapshot.library_root, "Library root"))
        resolver = await _resolver_config(settings_repository, snapshot)
    except SyncConfigurationError as error:
        _ = await sync_runs.record_failure(
            phase="configuration",
            message=str(error),
            source="auto",
            item_ref=torrent_id,
        )
        await session.commit()
        raise

    await session.commit()
    mutation_journal = LibraryMutationJournal.create(library_root)
    try:
        result, tmdb_api_key = await _generate_item_files(
            session,
            settings,
            settings_repository,
            api_key=api_key,
            library_root=library_root,
            resolver=resolver,
            torrent_id=torrent_id,
            client_factory=client_factory,
            mutation_journal=mutation_journal,
        )
    except Exception as error:
        await session.rollback()
        mutation_journal.restore()
        _ = await sync_runs.record_failure(
            phase="torbox_item_sync",
            message="New TorBox item could not be synchronized.",
            source="auto",
            item_ref=torrent_id,
        )
        await session.commit()
        raise SyncExecutionError("New TorBox item sync failed.") from error

    try:
        sync_run_id = await sync_runs.record_success(result, source="auto")
        _ = await SyncLibraryStateRepository(session).persist_result(result, library_root)
        await session.commit()
    except Exception as error:
        await session.rollback()
        mutation_journal.restore()
        _ = await sync_runs.record_failure(
            phase="persistence",
            message="Incremental sync persistence failed; generated files were restored.",
            source="auto",
            item_ref=torrent_id,
            scanned_count=result.scanned_files,
            written_count=result.written_files,
            skipped_count=result.skipped_files,
        )
        await session.commit()
        raise SyncExecutionError("Incremental sync persistence failed.") from error

    await _cache_item_posters(settings, library_root, result.synced_files, tmdb_api_key)
    logger.debug(
        "Incremental TorBox sync completed item_id=%s scanned=%d written=%d skipped=%d.",
        torrent_id,
        result.scanned_files,
        result.written_files,
        result.skipped_files,
    )
    return SyncRunSummary(
        sync_run_id=sync_run_id,
        playback_mode=snapshot.playback_mode,
        library_root=str(library_root),
        scanned_files=result.scanned_files,
        written_files=result.written_files,
        skipped_files=result.skipped_files,
    )


async def _generate_item_files(  # noqa: PLR0913
    session: AsyncSession,
    settings: Settings,
    settings_repository: AppSettingsRepository,
    *,
    api_key: str,
    library_root: Path,
    resolver: ResolverUrlConfig | None,
    torrent_id: str,
    client_factory: TorBoxClientFactory,
    mutation_journal: LibraryMutationJournal,
) -> tuple[TorBoxStrmSyncResult, str | None]:
    async with client_factory(
        api_key=api_key,
        base_url=settings.torbox_base_url,
        timeout=settings.outbound_timeout_seconds,
    ) as client:
        item = await client.get_download("torrents", torrent_id)
        if item is None:
            msg = "The new TorBox torrent is not visible yet."
            raise SyncExecutionError(msg)

        selections = StreamSelectionRepository(session)
        selected = await selections.selected_for_torbox_item(torrent_id)
        tmdb_api_key = await settings_repository.provider_api_key("tmdb")
        identity_resolver = MediaIdentityResolver(_tmdb_service(session, settings, tmdb_api_key))
        by_torrent_id, by_info_hash = await selected_media_identities(
            selections,
            selected,
            identity_resolver,
        )
        identity_inputs = IdentityInputs(by_torrent_id, by_info_hash, {})
        classification_overrides = await ClassificationOverrideRepository(session).list_all()
        excluded_prefixes = await LibraryExclusionRepository(session).prefixes()
        await session.commit()

        info_hash = torrent_info_hash(item)
        result = await TorBoxStrmSync(
            client=_SingleTorrentClient(item),
            api_key=api_key,
            torbox_base_url=settings.torbox_base_url,
            library_root=library_root,
            resolver=resolver,
            anime_classifier=build_anilist_anime_classifier(session, settings),
            classification_overrides=classification_overrides,
            excluded_prefixes=excluded_prefixes,
            media_identity_resolver=identity_resolver,
            torrent_hashes={torrent_id: info_hash} if info_hash is not None else {},
            identity_inputs=identity_inputs,
            mutation_tracker=mutation_journal,
        ).run(kinds=("torrents",), partial=True)
    return result, tmdb_api_key


def _tmdb_service(
    session: AsyncSession,
    settings: Settings,
    api_key: str | None,
) -> TmdbMetadataService | None:
    if api_key is None:
        return None
    return TmdbMetadataService(
        cache_repository=TmdbCacheRepository(session),
        tmdb_client=TmdbClient(
            api_key=api_key,
            base_url=settings.tmdb_base_url,
            timeout_seconds=settings.outbound_timeout_seconds,
        ),
    )


async def _resolver_config(
    repository: AppSettingsRepository,
    snapshot: SettingsSnapshot,
) -> ResolverUrlConfig | None:
    if snapshot.playback_mode == "direct":
        return None
    base_url = _required(snapshot.base_url, "Base URL")
    resolver_token = _required(await repository.resolver_token_value(), "Resolver token")
    return ResolverUrlConfig(base_url=base_url, token=resolver_token)


def _required(value: str | None, label: str) -> str:
    if value is None:
        raise SyncConfigurationError(f"{label} is not configured.")
    return value


async def _cache_item_posters(
    settings: Settings,
    library_root: Path,
    synced_files: tuple[SyncedStrmFile, ...],
    tmdb_api_key: str | None,
) -> None:
    if tmdb_api_key is None:
        return
    _ = await cache_missing_posters(
        library_root,
        synced_files,
        TmdbPosterClient(timeout_seconds=settings.outbound_timeout_seconds),
    )
