from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    LibraryEntry,
    PlaybackAttempt,
    ResolverToken,
    TorBoxStoredFile,
)
from app.db.repositories.settings import sha256_hex
from app.operations.metrics import get_operational_metrics
from app.providers.torbox.client import TorBoxAPIError
from app.providers.torbox.files import (
    DOWNLOAD_KINDS,
    DownloadKind,
    TorBoxFile,
    extract_torbox_files,
    request_download_url,
)

PLAYBACK_RECOVERY_ATTEMPTS = 30
PLAYBACK_RECOVERY_INTERVAL_SECONDS = 2.0


class ResolverLookupError(RuntimeError):
    """Raised when a database-backed resolver target cannot be built."""


class ResolverRecoveryError(RuntimeError):
    """Raised when a stale TorBox playback target cannot be restored."""


class TorBoxPlaybackClient(Protocol):
    async def request_download_link(self, torbox_file: TorBoxFile) -> str: ...

    async def find_torrent_by_hash(self, info_hash: str) -> dict[str, Any] | None: ...

    async def create_torrent(
        self,
        *,
        magnet: str,
        name: str | None = None,
        add_only_if_cached: bool = True,
    ) -> dict[str, Any]: ...

    async def get_download(
        self,
        kind: DownloadKind,
        item_id: str,
    ) -> dict[str, Any] | None: ...


@dataclass(frozen=True, slots=True)
class ResolverTarget:
    target_url: str


class PlaybackResolverRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolver_token_is_valid(self, token: str) -> bool:
        result = await self._session.execute(
            select(ResolverToken.id).where(
                ResolverToken.token_hash == sha256_hex(token),
                ResolverToken.revoked_at.is_(None),
            )
        )
        return result.scalar_one_or_none() is not None

    async def resolve_torbox_target(
        self,
        *,
        entry_id: str,
        api_key: str,
        torbox_base_url: str,
        torbox_client: TorBoxPlaybackClient | None = None,
    ) -> ResolverTarget:
        library_entry = await self._library_entry(entry_id)
        if library_entry is None:
            await self._record_attempt(
                entry_id=entry_id,
                library_entry=None,
                status="not_found",
                failure_reason="library_entry_not_found",
            )
            msg = "Resolver entry was not found."
            raise ResolverLookupError(msg)

        saved_file = _saved_torbox_file(library_entry)
        if saved_file is None:
            await self._record_attempt(
                entry_id=entry_id,
                library_entry=library_entry,
                status="failed",
                failure_reason="unsupported_provider",
            )
            msg = "Resolver entry provider is not supported."
            raise ResolverLookupError(msg)

        try:
            target_url = await self._playback_target(
                saved_file=saved_file,
                info_hash=library_entry.info_hash,
                api_key=api_key,
                torbox_base_url=torbox_base_url,
                torbox_client=torbox_client,
            )
        except (ResolverRecoveryError, TorBoxAPIError):
            await self._record_attempt(
                entry_id=entry_id,
                library_entry=library_entry,
                status="failed",
                failure_reason="torbox_recovery_failed",
            )
            raise
        await self._record_attempt(
            entry_id=entry_id,
            library_entry=library_entry,
            status="redirect",
            failure_reason=None,
        )
        return ResolverTarget(target_url=target_url)

    async def _playback_target(
        self,
        *,
        saved_file: TorBoxFile,
        info_hash: str | None,
        api_key: str,
        torbox_base_url: str,
        torbox_client: TorBoxPlaybackClient | None,
    ) -> str:
        if torbox_client is None or saved_file.kind != "torrents":
            return request_download_url(torbox_base_url, api_key, saved_file)

        if info_hash is None:
            return request_download_url(torbox_base_url, api_key, saved_file)

        try:
            return await torbox_client.request_download_link(saved_file)
        except TorBoxAPIError:
            pass

        metrics = get_operational_metrics()
        metrics.resolver_recovery_started()
        try:
            recovered_file = await _recover_torrent_file(
                torbox_client,
                info_hash,
                saved_file.folder_name or saved_file.file_name,
                saved_file,
            )
            target_url = await torbox_client.request_download_link(recovered_file)
        except (ResolverRecoveryError, TorBoxAPIError) as error:
            metrics.resolver_recovery_finished(succeeded=False)
            if isinstance(error, ResolverRecoveryError):
                raise
            msg = "TorBox playback recovery failed."
            raise ResolverRecoveryError(msg) from error
        metrics.resolver_recovery_finished(succeeded=True)
        return target_url

    async def _library_entry(self, entry_id: str) -> LibraryEntry | None:
        result = await self._session.execute(
            select(LibraryEntry)
            .options(
                selectinload(LibraryEntry.torbox_file).selectinload(TorBoxStoredFile.torbox_item)
            )
            .where(LibraryEntry.opaque_id == entry_id)
        )
        return result.scalar_one_or_none()

    async def _record_attempt(
        self,
        *,
        entry_id: str,
        library_entry: LibraryEntry | None,
        status: str,
        failure_reason: str | None,
    ) -> None:
        self._session.add(
            PlaybackAttempt(
                library_entry_id=library_entry.id if library_entry is not None else None,
                entry_opaque_id=entry_id,
                status=status,
                failure_reason=failure_reason,
            )
        )
        await self._session.flush()


def _torbox_kind(kind: str) -> DownloadKind | None:
    return kind if kind in DOWNLOAD_KINDS else None


def _saved_torbox_file(library_entry: LibraryEntry) -> TorBoxFile | None:
    torbox_file = library_entry.torbox_file
    if torbox_file is not None:
        kind = _torbox_kind(torbox_file.torbox_item.kind)
        if kind is None:
            return None
        return TorBoxFile(
            kind=kind,
            item_id=torbox_file.torbox_item.external_id,
            file_id=torbox_file.external_id,
            folder_name=torbox_file.torbox_item.name,
            file_name=torbox_file.file_name,
            path=torbox_file.path,
            mime_type=torbox_file.mime_type,
            size=torbox_file.size,
        )

    kind = _torbox_kind(library_entry.source_kind or "")
    if (
        kind is None
        or library_entry.source_item_id is None
        or library_entry.source_file_id is None
        or library_entry.source_file_name is None
    ):
        return None
    return TorBoxFile(
        kind=kind,
        item_id=library_entry.source_item_id,
        file_id=library_entry.source_file_id,
        folder_name=library_entry.source_item_name or "",
        file_name=library_entry.source_file_name,
        path=library_entry.source_file_path or library_entry.source_file_name,
        mime_type=library_entry.source_file_mime_type or "",
        size=library_entry.source_file_size,
    )


async def _recover_torrent_file(
    client: TorBoxPlaybackClient,
    info_hash: str,
    title: str,
    saved_file: TorBoxFile,
) -> TorBoxFile:
    torrent, torrent_id = await _find_or_create_torrent(client, info_hash, title)

    for attempt in range(PLAYBACK_RECOVERY_ATTEMPTS):
        if torrent is not None and _torrent_is_ready(torrent):
            match = _matching_file(torrent, saved_file)
            if match is not None:
                return match
        if attempt + 1 == PLAYBACK_RECOVERY_ATTEMPTS:
            break
        await asyncio.sleep(PLAYBACK_RECOVERY_INTERVAL_SECONDS)
        if torrent_id is not None:
            torrent = await client.get_download("torrents", torrent_id)
        else:
            torrent = await client.find_torrent_by_hash(info_hash)
            torrent_id = _item_id(torrent)

    msg = "TorBox playback recovery did not produce the saved media file."
    raise ResolverRecoveryError(msg)


async def _find_or_create_torrent(
    client: TorBoxPlaybackClient,
    info_hash: str,
    title: str,
) -> tuple[dict[str, Any] | None, str | None]:
    torrent = await client.find_torrent_by_hash(info_hash)
    if torrent is not None:
        return torrent, _item_id(torrent)
    try:
        created = await client.create_torrent(
            magnet=f"magnet:?xt=urn:btih:{info_hash}",
            name=title,
            add_only_if_cached=True,
        )
    except TorBoxAPIError as error:
        if error.error_code != "DUPLICATE_ITEM":
            raise
        return None, None
    return None, _created_torrent_id(created)


def _matching_file(torrent: dict[str, Any], saved_file: TorBoxFile) -> TorBoxFile | None:
    candidates = extract_torbox_files([torrent], "torrents").files
    saved_path = _normalized_path(saved_file.path)
    for candidate in candidates:
        if _normalized_path(candidate.path) == saved_path:
            return candidate

    matching_names = [
        candidate
        for candidate in candidates
        if candidate.file_name.casefold() == saved_file.file_name.casefold()
    ]
    if saved_file.size is not None:
        same_size = [candidate for candidate in matching_names if candidate.size == saved_file.size]
        if len(same_size) == 1:
            return same_size[0]
    if len(matching_names) == 1:
        return matching_names[0]
    return None


def _torrent_is_ready(torrent: dict[str, Any]) -> bool:
    download_finished = torrent.get("download_finished")
    if isinstance(download_finished, bool):
        return download_finished
    state = torrent.get("download_state")
    if isinstance(state, str) and state.strip():
        return state.casefold() in {"cached", "completed", "uploading"}
    return torrent.get("cached") is not False and isinstance(torrent.get("files"), list)


def _item_id(item: dict[str, Any] | None) -> str | None:
    return _string_id(item.get("id")) if item is not None else None


def _created_torrent_id(item: dict[str, Any]) -> str | None:
    return _string_id(item.get("torrent_id")) or _string_id(item.get("id"))


def _string_id(value: object) -> str | None:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _normalized_path(value: str) -> str:
    return value.replace("\\", "/").strip("/").casefold()
