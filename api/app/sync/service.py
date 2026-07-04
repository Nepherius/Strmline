from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.repositories.settings import AppSettingsRepository, SettingsSnapshot
from app.db.repositories.sync_state import SyncStateRepository
from app.providers.torbox.client import TorBoxAPIError, TorBoxClient
from app.sync.torbox_strm import ResolverUrlConfig, TorBoxStrmSync


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


async def run_torbox_account_sync(
    session: AsyncSession,
    settings: Settings,
    *,
    client_factory: TorBoxClientFactory = TorBoxClient,
) -> SyncRunSummary:
    if _SYNC_LOCK.locked():
        msg = "A sync run is already in progress."
        raise SyncAlreadyRunningError(msg)

    async with _SYNC_LOCK:
        return await _run_torbox_account_sync(session, settings, client_factory=client_factory)


async def _run_torbox_account_sync(
    session: AsyncSession,
    settings: Settings,
    *,
    client_factory: TorBoxClientFactory,
) -> SyncRunSummary:
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
        _ = await sync_state.record_failure(phase="configuration", message=str(error))
        raise

    try:
        async with client_factory(
            api_key=api_key,
            base_url=settings.torbox_base_url,
            timeout=settings.outbound_timeout_seconds,
        ) as client:
            result = await TorBoxStrmSync(
                client=client,
                api_key=api_key,
                torbox_base_url=settings.torbox_base_url,
                library_root=library_root,
                resolver=resolver,
            ).run()
    except (OSError, TorBoxAPIError, ValueError) as error:
        _ = await sync_state.record_failure(
            phase="torbox_sync", message=_safe_failure_message(error)
        )
        raise SyncExecutionError("TorBox sync failed.") from error

    sync_run_id = await sync_state.record_success(result, library_root)
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
