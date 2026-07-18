from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.repositories.classification_override import ClassificationOverrideRepository
from app.db.repositories.library_exclusion import LibraryExclusionRepository
from app.db.repositories.settings import AppSettingsRepository, SettingsSnapshot
from app.db.repositories.stream_selection import StreamSelectionRepository
from app.db.repositories.sync_coordination import SyncCoordinationRepository
from app.db.repositories.sync_runs import SyncRunRepository, SyncRunSource
from app.db.repositories.sync_state import SyncLibraryStateRepository
from app.db.repositories.tmdb_cache import TmdbCacheRepository
from app.db.repositories.watchlist import WatchlistRepository
from app.library.posters import cache_missing_posters
from app.library.stale_cleanup import remove_stale_strm_files
from app.library.sync_snapshot import LibrarySyncSnapshot
from app.providers.aiostreams.client import AioStreamsClient
from app.providers.tmdb.client import TmdbClient
from app.providers.tmdb.metadata import TmdbMetadataService
from app.providers.tmdb.posters import TmdbPosterClient
from app.providers.torbox.client import TorBoxAPIError, TorBoxClient
from app.search.actions import ensure_selected_streams_in_torbox
from app.sync.anime_classification import build_anilist_anime_classifier
from app.sync.identity_inputs import identity_inputs as _identity_inputs
from app.sync.media_identity import MediaIdentityResolver
from app.sync.torbox_strm import ResolverUrlConfig, TorBoxStrmSync, TorBoxStrmSyncResult


class SyncAlreadyRunningError(RuntimeError):
    """Raised when a sync run is already active."""


class SyncConfigurationError(RuntimeError):
    """Raised when required sync configuration is missing."""


class SyncExecutionError(RuntimeError):
    """Raised when sync execution fails."""


class TorBoxClientFactory(Protocol):
    def __call__(self, *, api_key: str, base_url: str, timeout: float) -> TorBoxClient:
        """Build a TorBox client context manager."""
        ...


@dataclass(frozen=True, slots=True)
class SyncRunSummary:
    sync_run_id: int
    playback_mode: str
    library_root: str
    scanned_files: int
    written_files: int
    skipped_files: int


@dataclass(frozen=True, slots=True)
class _GeneratedSync:
    result: TorBoxStrmSyncResult
    selected_hashes: frozenset[str]
    tmdb_api_key: str | None


logger = logging.getLogger(__name__)


async def run_torbox_account_sync(
    session: AsyncSession,
    settings: Settings,
    *,
    source: SyncRunSource = "manual",
    client_factory: TorBoxClientFactory = TorBoxClient,
) -> SyncRunSummary:
    logger.debug("Starting TorBox account sync from %s.", source)
    coordination = SyncCoordinationRepository(session)
    if not await coordination.try_lock():
        raise SyncAlreadyRunningError("A sync run is already in progress.")
    try:
        return await _execute_sync(
            session,
            settings,
            source=source,
            client_factory=client_factory,
        )
    finally:
        await coordination.release()


async def _execute_sync(
    session: AsyncSession,
    settings: Settings,
    *,
    source: SyncRunSource,
    client_factory: TorBoxClientFactory,
) -> SyncRunSummary:
    sync_state = SyncLibraryStateRepository(session)
    sync_runs = SyncRunRepository(session)
    settings_repository = AppSettingsRepository(session, settings)
    snapshot = await settings_repository.snapshot_with_env()
    api_key = await settings_repository.provider_api_key("torbox")
    try:
        api_key = _require_torbox_api_key(api_key)
        resolver_token = await settings_repository.resolver_token_value()
        library_root = _library_root(snapshot)
        resolver = _resolver_config(snapshot, resolver_token)
    except SyncConfigurationError as error:
        _ = await sync_runs.record_failure(
            phase="configuration",
            message=str(error),
            source=source,
        )
        await session.commit()
        raise

    # End the configuration read transaction before any provider request begins.
    await session.commit()

    file_snapshot = LibrarySyncSnapshot.capture(library_root)
    try:
        generated = await _generate_sync_files(
            session,
            settings,
            settings_repository,
            api_key=api_key,
            library_root=library_root,
            resolver=resolver,
            client_factory=client_factory,
        )
    except Exception as error:
        await session.rollback()
        file_snapshot.restore()
        _ = await sync_runs.record_failure(
            phase="torbox_sync",
            message=_safe_failure_message(error),
            source=source,
        )
        await session.commit()
        raise SyncExecutionError("TorBox sync failed.") from error

    result = generated.result
    try:
        retained_paths = await sync_state.retained_library_paths(
            library_root,
            _absent_selected_hashes(generated.selected_hashes, result),
        )
        await _remove_synced_from_watchlist(session, result)
        sync_run_id = await sync_runs.record_success(result, source=source)
        await sync_state.persist_result(
            result,
            library_root,
            retained_info_hashes=generated.selected_hashes,
        )
        await session.commit()
    except Exception as error:
        await session.rollback()
        file_snapshot.restore()
        _ = await sync_runs.record_failure(
            phase="persistence",
            message="Database persistence failed; generated files were restored.",
            source=source,
            scanned_count=result.scanned_files,
            written_count=result.written_files,
            skipped_count=result.skipped_files,
        )
        await session.commit()
        raise SyncExecutionError(
            "Sync persistence failed; generated files were restored."
        ) from error
    _remove_stale_sync_files(library_root, result, retained_paths)
    await _cache_missing_sync_posters(settings, library_root, result, generated.tmdb_api_key)
    logger.debug(
        "Completed TorBox account sync from %s: %d scanned, %d written, %d skipped.",
        source,
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


async def _generate_sync_files(  # noqa: PLR0913
    session: AsyncSession,
    settings: Settings,
    settings_repository: AppSettingsRepository,
    *,
    api_key: str,
    library_root: Path,
    resolver: ResolverUrlConfig | None,
    client_factory: TorBoxClientFactory,
) -> _GeneratedSync:
    async with client_factory(
        api_key=api_key,
        base_url=settings.torbox_base_url,
        timeout=settings.outbound_timeout_seconds,
    ) as client:
        aiostreams_url = await settings_repository.aiostreams_base_url_value()
        selections = StreamSelectionRepository(session)
        await ensure_selected_streams_in_torbox(
            torbox_client=client,
            repository=selections,
            aiostreams_client=(
                AioStreamsClient(
                    base_url=aiostreams_url,
                    timeout_seconds=settings.outbound_timeout_seconds,
                )
                if aiostreams_url is not None
                else None
            ),
        )
        await session.commit()
        selected_streams = await selections.list_selected()
        selected_hashes = frozenset(
            selection.info_hash.casefold()
            for selection in selected_streams
            if selection.info_hash is not None
        )
        torrent_hashes = {
            selection.torbox_torrent_id: selection.info_hash.casefold()
            for selection in selected_streams
            if selection.torbox_torrent_id is not None and selection.info_hash is not None
        }
        tmdb_api_key = await settings_repository.provider_api_key("tmdb")
        tmdb_service = _tmdb_service(session, settings, tmdb_api_key)
        identity_resolver = MediaIdentityResolver(tmdb_service)
        identities = await _identity_inputs(
            session,
            selections,
            selected_streams,
            identity_resolver,
        )
        classification_overrides = await ClassificationOverrideRepository(session).list_all()
        excluded_prefixes = await LibraryExclusionRepository(session).prefixes()
        # Provider enumeration can be slow. Do not retain the input-read transaction.
        await session.commit()
        result = await TorBoxStrmSync(
            client=client,
            api_key=api_key,
            torbox_base_url=settings.torbox_base_url,
            library_root=library_root,
            resolver=resolver,
            anime_classifier=build_anilist_anime_classifier(session, settings),
            classification_overrides=classification_overrides,
            excluded_prefixes=excluded_prefixes,
            media_identity_resolver=identity_resolver,
            torrent_hashes=torrent_hashes,
            identity_inputs=identities,
        ).run()
    return _GeneratedSync(
        result=result,
        selected_hashes=selected_hashes,
        tmdb_api_key=tmdb_api_key,
    )


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


async def _cache_missing_sync_posters(
    settings: Settings,
    library_root: Path,
    result: TorBoxStrmSyncResult,
    tmdb_api_key: str | None,
) -> None:
    if tmdb_api_key is None:
        return
    poster_result = await cache_missing_posters(
        library_root,
        result.synced_files,
        TmdbPosterClient(timeout_seconds=settings.outbound_timeout_seconds),
    )
    logger.debug(
        "TMDB poster cache: %d downloaded, %d already cached, %d failed.",
        poster_result.downloaded,
        poster_result.cached,
        poster_result.failed,
    )


def _remove_stale_sync_files(
    library_root: Path,
    result: TorBoxStrmSyncResult,
    preserved_paths: set[Path],
) -> None:
    if result.partial:
        return
    remove_stale_strm_files(
        library_root,
        set(result.written_paths) | preserved_paths,
    )


def _library_root(snapshot: SettingsSnapshot) -> Path:
    if snapshot.library_root is None:
        raise SyncConfigurationError("Library root is not configured.")
    return Path(snapshot.library_root)


def _watchlist_identities(result: TorBoxStrmSyncResult) -> set[tuple[str, int]]:
    identities: set[tuple[str, int]] = set()
    for synced_file in result.synced_files:
        if synced_file.tmdb_id is None or not synced_file.tmdb_id.isdecimal():
            continue
        media_type = "movie" if synced_file.category == "movies" else "series"
        identities.add((media_type, int(synced_file.tmdb_id)))
    return identities


def _result_info_hashes(result: TorBoxStrmSyncResult) -> frozenset[str]:
    return frozenset(
        synced_file.info_hash
        for synced_file in result.synced_files
        if synced_file.info_hash is not None
    )


def _absent_selected_hashes(
    selected_hashes: frozenset[str],
    result: TorBoxStrmSyncResult,
) -> frozenset[str]:
    """Retain only selected media that is absent from the current provider result."""
    return selected_hashes - _result_info_hashes(result)


async def _remove_synced_from_watchlist(
    session: AsyncSession,
    result: TorBoxStrmSyncResult,
) -> None:
    identities = _watchlist_identities(result)
    if identities:
        _ = await WatchlistRepository(session).delete_identities(identities)


def _require_torbox_api_key(api_key: str | None) -> str:
    if api_key is None:
        raise SyncConfigurationError("TorBox API key is not configured.")
    return api_key


def _resolver_config(
    snapshot: SettingsSnapshot,
    resolver_token: str | None,
) -> ResolverUrlConfig | None:
    if snapshot.playback_mode == "direct":
        return None
    if snapshot.base_url is None:
        raise SyncConfigurationError("Base URL is required for resolver playback mode.")
    if resolver_token is None:
        raise SyncConfigurationError("Resolver token is required to generate resolver STRM files.")
    return ResolverUrlConfig(
        base_url=snapshot.base_url,
        token=resolver_token,
    )


def _safe_failure_message(error: Exception) -> str:
    if isinstance(error, TorBoxAPIError):
        return str(error) or "TorBox API request failed."
    if isinstance(error, OSError):
        return "Filesystem error while writing generated STRM files."
    if isinstance(error, ValueError):
        return str(error) or "Sync input validation failed."
    return "TorBox sync failed."
