from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LibraryEntry, PlaybackAttempt, ResolverToken
from app.db.repositories.settings import sha256_hex
from app.providers.torbox.files import (
    DOWNLOAD_KINDS,
    DownloadKind,
    TorBoxFile,
    request_download_url,
)
from app.resolver.manifest import resolver_entry_id


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

        kind = _torbox_kind(library_entry)
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
                item_id=library_entry.provider_item_id,
                file_id=library_entry.provider_file_id,
                folder_name="",
                file_name="",
                path="",
                mime_type="",
                size=None,
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
            select(LibraryEntry).where(LibraryEntry.opaque_id == entry_id)
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


def _torbox_kind(library_entry: LibraryEntry) -> DownloadKind | None:
    if library_entry.provider in DOWNLOAD_KINDS:
        return library_entry.provider
    if library_entry.provider.startswith("torbox:"):
        candidate = library_entry.provider.split(":", maxsplit=1)[1]
        if candidate in DOWNLOAD_KINDS:
            return candidate
    if library_entry.provider != "torbox":
        return None
    return _legacy_torbox_kind(library_entry)


def _legacy_torbox_kind(library_entry: LibraryEntry) -> DownloadKind | None:
    for kind in DOWNLOAD_KINDS:
        candidate = TorBoxFile(
            kind=kind,
            item_id=library_entry.provider_item_id,
            file_id=library_entry.provider_file_id,
            folder_name="",
            file_name="",
            path="",
            mime_type="",
            size=None,
        )
        if resolver_entry_id(candidate) == library_entry.opaque_id:
            return kind
    return None
