from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.repositories.classification_override import ClassificationOverrideRepository
from app.db.repositories.library_exclusion import LibraryExclusionRepository
from app.db.repositories.settings import AppSettingsRepository, SettingsSnapshot
from app.db.repositories.stream_selection import StreamSelectionRecord, StreamSelectionRepository
from app.db.repositories.sync_state import SyncRunSource, SyncStateRepository
from app.db.repositories.tmdb_cache import TmdbCacheRepository
from app.db.repositories.watchlist import WatchlistRepository
from app.library.posters import cache_missing_posters
from app.providers.aiostreams.client import AioStreamsClient
from app.providers.tmdb.client import TmdbClient
from app.providers.tmdb.metadata import TmdbMetadataService
from app.providers.tmdb.posters import TmdbPosterClient
from app.providers.torbox.client import TorBoxAPIError, TorBoxClient
from app.search.actions import ensure_selected_streams_in_torbox
from app.sync.anime_classification import build_anilist_anime_classifier
from app.sync.media_identity import MediaIdentity, MediaIdentityResolver
from app.sync.torbox_strm import ResolverUrlConfig, TorBoxStrmSync, TorBoxStrmSyncResult


class SyncAlreadyRunningError(RuntimeError):
    """Raised when a sync run is already active in this process."""


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


_SYNC_LOCK = asyncio.Lock()
logger = logging.getLogger(__name__)


async def run_torbox_account_sync(
    session: AsyncSession,
    settings: Settings,
    *,
    source: SyncRunSource = "manual",
    client_factory: TorBoxClientFactory = TorBoxClient,
) -> SyncRunSummary:
    if _SYNC_LOCK.locked():
        msg = "A sync run is already in progress."
        raise SyncAlreadyRunningError(msg)

    async with _SYNC_LOCK:
        return await _run_torbox_account_sync(
            session,
            settings,
            source=source,
            client_factory=client_factory,
        )


async def _run_torbox_account_sync(
    session: AsyncSession,
    settings: Settings,
    *,
    source: SyncRunSource,
    client_factory: TorBoxClientFactory,
) -> SyncRunSummary:
    logger.debug("Starting TorBox account sync from %s.", source)
    sync_state = SyncStateRepository(session)
    settings_repository = AppSettingsRepository(session, settings)
    snapshot = await settings_repository.snapshot_with_env()
    api_key = await settings_repository.provider_api_key("torbox")
    try:
        api_key = _require_torbox_api_key(api_key)
        resolver_token = await settings_repository.resolver_token_value()
        library_root = _library_root(snapshot)
        resolver = _resolver_config(snapshot, resolver_token)
    except SyncConfigurationError as error:
        _ = await sync_state.record_failure(
            phase="configuration",
            message=str(error),
            source=source,
        )
        raise

    try:
        async with client_factory(
            api_key=api_key,
            base_url=settings.torbox_base_url,
            timeout=settings.outbound_timeout_seconds,
        ) as client:
            aiostreams_url = await settings_repository.aiostreams_base_url_value()
            selection_repository = StreamSelectionRepository(session)
            await ensure_selected_streams_in_torbox(
                torbox_client=client,
                repository=selection_repository,
                aiostreams_client=(
                    AioStreamsClient(
                        base_url=aiostreams_url,
                        timeout_seconds=settings.outbound_timeout_seconds,
                    )
                    if aiostreams_url is not None
                    else None
                ),
            )
            selected_streams = await selection_repository.list_selected()
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
            permanent_info_hashes = await sync_state.permanent_info_hashes()
            preserved_paths = await sync_state.permanent_library_paths(
                library_root,
                permanent_info_hashes,
            )
            tmdb_api_key = await settings_repository.provider_api_key("tmdb")
            tmdb_service = None
            if tmdb_api_key:
                tmdb_service = TmdbMetadataService(
                    cache_repository=TmdbCacheRepository(session),
                    tmdb_client=TmdbClient(
                        api_key=tmdb_api_key,
                        base_url=settings.tmdb_base_url,
                        timeout_seconds=settings.outbound_timeout_seconds,
                    ),
                )
            identity_resolver = MediaIdentityResolver(tmdb_service)
            (
                selected_media_by_torrent_id,
                selected_media_by_info_hash,
            ) = await _selected_media_identities(
                selection_repository,
                selected_streams,
                identity_resolver,
            )

            result = await TorBoxStrmSync(
                client=client,
                api_key=api_key,
                torbox_base_url=settings.torbox_base_url,
                library_root=library_root,
                resolver=resolver,
                anime_classifier=build_anilist_anime_classifier(session, settings),
                classification_overrides=await ClassificationOverrideRepository(session).list_all(),
                excluded_prefixes=await LibraryExclusionRepository(session).prefixes(),
                media_identity_resolver=identity_resolver,
                torrent_hashes=torrent_hashes,
                selected_media_by_torrent_id=selected_media_by_torrent_id,
                selected_media_by_info_hash=selected_media_by_info_hash,
                preserved_paths=preserved_paths,
            ).run()
    except (OSError, TorBoxAPIError, ValueError) as error:
        _ = await sync_state.record_failure(
            phase="torbox_sync",
            message=_safe_failure_message(error),
            source=source,
        )
        raise SyncExecutionError("TorBox sync failed.") from error

    await _remove_synced_from_watchlist(session, result)

    sync_run_id = await sync_state.record_success(
        result,
        library_root,
        source=source,
        permanent_info_hashes=(
            permanent_info_hashes
            | selected_hashes
            | frozenset(
                synced_file.info_hash
                for synced_file in result.synced_files
                if synced_file.info_hash is not None
            )
        ),
    )
    if tmdb_api_key is not None:
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


async def _selected_media_identities(
    repository: StreamSelectionRepository,
    selections: tuple[StreamSelectionRecord, ...],
    resolver: MediaIdentityResolver,
) -> tuple[dict[str, MediaIdentity], dict[str, MediaIdentity]]:
    by_torrent_id: dict[str, MediaIdentity] = {}
    by_info_hash: dict[str, MediaIdentity] = {}
    resolved_external_ids: dict[tuple[str, str], MediaIdentity | None] = {}
    for selection in selections:
        identity = _stored_media_identity(selection)
        if identity is None:
            external_id = selection.media_id.split(":", maxsplit=1)[0]
            external_key = (external_id, selection.media_type)
            if external_key not in resolved_external_ids:
                resolved_external_ids[external_key] = await resolver.resolve_external_id(
                    external_id,
                    selection.media_type,
                )
            identity = resolved_external_ids[external_key]
            if identity is not None and identity.tmdb_id is not None:
                await repository.update_media_identity(
                    selection.stream_key,
                    tmdb_id=identity.tmdb_id,
                    media_title=identity.title,
                    media_year=identity.year,
                    media_poster_path=identity.poster_path,
                )
        if identity is None or identity.tmdb_id is None:
            continue
        if selection.torbox_torrent_id is not None:
            by_torrent_id[selection.torbox_torrent_id] = identity
        if selection.info_hash is not None:
            by_info_hash[selection.info_hash.casefold()] = identity
    return by_torrent_id, by_info_hash


def _stored_media_identity(selection: StreamSelectionRecord) -> MediaIdentity | None:
    if selection.tmdb_id is None or selection.media_title is None:
        return None
    return MediaIdentity(
        tmdb_id=selection.tmdb_id,
        title=selection.media_title,
        year=selection.media_year,
        media_type="movie" if selection.media_type == "movie" else "tv",
        poster_path=selection.media_poster_path,
    )


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
