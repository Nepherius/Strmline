from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GeneratedFile, LibraryEntry, LibraryExclusion, TorBoxItem
from app.providers.torbox.files import DOWNLOAD_KINDS, DownloadKind


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
            select(TorBoxItem)
            .select_from(GeneratedFile)
            .join(LibraryEntry)
            .join(LibraryEntry.torbox_file)
            .join(TorBoxItem)
            .where(
                or_(
                    GeneratedFile.relative_path == relative_prefix,
                    GeneratedFile.relative_path.like(f"{relative_prefix}/%"),
                )
            )
        )
        items: dict[tuple[DownloadKind, str], BackingProviderItem] = {}
        for torbox_item in result.scalars():
            kind = _torbox_kind(torbox_item.kind)
            if kind is None:
                continue
            key = (kind, torbox_item.external_id)
            items[key] = BackingProviderItem(kind=kind, item_id=torbox_item.external_id)
        return tuple(items.values())


def _torbox_kind(kind: str) -> DownloadKind | None:
    return kind if kind in DOWNLOAD_KINDS else None
