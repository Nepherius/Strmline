from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GeneratedFile, LibraryEntry, LibraryExclusion
from app.providers.torbox.files import DOWNLOAD_KINDS, DownloadKind, TorBoxFile
from app.resolver.manifest import resolver_entry_id


@dataclass(frozen=True, slots=True)
class BackingProviderItem:
    kind: DownloadKind
    item_id: str


class LibraryExclusionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def prefixes(self) -> tuple[str, ...]:
        result = await self._session.execute(select(LibraryExclusion.relative_prefix))
        return tuple(str(prefix) for prefix in result.scalars())

    async def add(self, *, category: str, title: str, relative_prefix: str) -> None:
        existing = await self._session.execute(
            select(LibraryExclusion).where(LibraryExclusion.relative_prefix == relative_prefix)
        )
        if existing.scalar_one_or_none() is not None:
            return
        self._session.add(
            LibraryExclusion(
                category=category,
                title=title,
                relative_prefix=relative_prefix,
            )
        )
        await self._session.flush()

    async def backing_items(self, relative_prefix: str) -> tuple[BackingProviderItem, ...]:
        result = await self._session.execute(
            select(LibraryEntry)
            .join(GeneratedFile)
            .where(
                or_(
                    GeneratedFile.relative_path == relative_prefix,
                    GeneratedFile.relative_path.like(f"{relative_prefix}/%"),
                )
            )
        )
        items: dict[tuple[DownloadKind, str], BackingProviderItem] = {}
        for entry in result.scalars():
            kind = _torbox_kind(entry)
            if kind is None:
                continue
            key = (kind, entry.provider_item_id)
            items[key] = BackingProviderItem(kind=kind, item_id=entry.provider_item_id)
        return tuple(items.values())


def _torbox_kind(entry: LibraryEntry) -> DownloadKind | None:
    if entry.provider in DOWNLOAD_KINDS:
        return entry.provider
    if entry.provider.startswith("torbox:"):
        candidate = entry.provider.split(":", maxsplit=1)[1]
        if candidate in DOWNLOAD_KINDS:
            return candidate
    if entry.provider != "torbox":
        return None
    return _legacy_torbox_kind(entry)


def _legacy_torbox_kind(entry: LibraryEntry) -> DownloadKind | None:
    for kind in DOWNLOAD_KINDS:
        candidate = TorBoxFile(
            kind=kind,
            item_id=entry.provider_item_id,
            file_id=entry.provider_file_id,
            folder_name="",
            file_name="",
            path="",
            mime_type="",
            size=None,
        )
        if resolver_entry_id(candidate) == entry.opaque_id:
            return kind
    return None
