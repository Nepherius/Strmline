from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import LibraryEntry, PlaybackAttempt, ResolverToken, TorBoxStoredFile
from app.db.repositories.settings import sha256_hex
from app.providers.torbox.files import (
    DOWNLOAD_KINDS,
    DownloadKind,
    TorBoxFile,
    request_download_url,
)


class ResolverLookupError(RuntimeError):
    """Raised when a database-backed resolver target cannot be built."""


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

        torbox_file = library_entry.torbox_file
        kind = _torbox_kind(torbox_file.torbox_item.kind)
        if kind is None:
            await self._record_attempt(
                entry_id=entry_id,
                library_entry=library_entry,
                status="failed",
                failure_reason="unsupported_provider",
            )
            msg = "Resolver entry provider is not supported."
            raise ResolverLookupError(msg)

        target_url = request_download_url(
            torbox_base_url,
            api_key,
            TorBoxFile(
                kind=kind,
                item_id=torbox_file.torbox_item.external_id,
                file_id=torbox_file.external_id,
                folder_name=torbox_file.torbox_item.name,
                file_name=torbox_file.file_name,
                path=torbox_file.path,
                mime_type=torbox_file.mime_type,
                size=torbox_file.size,
            ),
        )
        await self._record_attempt(
            entry_id=entry_id,
            library_entry=library_entry,
            status="redirect",
            failure_reason=None,
        )
        return ResolverTarget(target_url=target_url)

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
        await self._session.commit()


def _torbox_kind(kind: str) -> DownloadKind | None:
    return kind if kind in DOWNLOAD_KINDS else None
