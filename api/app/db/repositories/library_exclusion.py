from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GeneratedFile, LibraryEntry, LibraryExclusion, TorBoxItem
from app.db.repositories.media_metadata import LIKE_ESCAPE, escape_like
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

    async def remove(self, relative_prefix: str) -> bool:
        result = await self._session.execute(
            delete(LibraryExclusion)
            .where(LibraryExclusion.relative_prefix == relative_prefix)
            .returning(LibraryExclusion.id)
        )
        return result.scalar_one_or_none() is not None

    async def remove_generated_files(self, relative_prefix: str) -> int:
        escaped_prefix = escape_like(relative_prefix)
        result = await self._session.execute(
            delete(GeneratedFile)
            .where(
                or_(
                    GeneratedFile.relative_path == relative_prefix,
                    GeneratedFile.relative_path.like(
                        f"{escaped_prefix}/%",
                        escape=LIKE_ESCAPE,
                    ),
                )
            )
            .returning(GeneratedFile.id)
        )
        return len(tuple(result.scalars()))

    async def clear_unobserved(self, observed_prefixes: frozenset[str]) -> int:
        statement = delete(LibraryExclusion)
        if observed_prefixes:
            statement = statement.where(LibraryExclusion.relative_prefix.not_in(observed_prefixes))
        result = await self._session.execute(statement.returning(LibraryExclusion.id))
        return len(tuple(result.scalars()))

    async def clear_for_selected_media(
        self,
        *,
        media_type: str,
        title: str,
        year: int | None,
    ) -> int:
        categories = ("movies",) if media_type == "movie" else ("shows", "anime")
        titles = {title}
        if year is not None:
            titles.add(f"{title} ({year})")
        result = await self._session.execute(
            delete(LibraryExclusion)
            .where(
                LibraryExclusion.category.in_(categories),
                LibraryExclusion.title.in_(titles),
            )
            .returning(LibraryExclusion.id)
        )
        return len(tuple(result.scalars()))

    async def backing_items(self, relative_prefix: str) -> tuple[BackingProviderItem, ...]:
        escaped_prefix = escape_like(relative_prefix)
        result = await self._session.execute(
            select(TorBoxItem)
            .select_from(GeneratedFile)
            .join(LibraryEntry)
            .join(LibraryEntry.torbox_file)
            .join(TorBoxItem)
            .where(
                or_(
                    GeneratedFile.relative_path == relative_prefix,
                    GeneratedFile.relative_path.like(
                        f"{escaped_prefix}/%",
                        escape=LIKE_ESCAPE,
                    ),
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

    async def backing_items_for_media(
        self,
        media_item_id: int,
    ) -> tuple[BackingProviderItem, ...]:
        result = await self._session.execute(
            select(TorBoxItem)
            .select_from(LibraryEntry)
            .join(LibraryEntry.torbox_file)
            .join(TorBoxItem)
            .where(LibraryEntry.media_item_id == media_item_id)
        )
        items: dict[tuple[DownloadKind, str], BackingProviderItem] = {}
        for torbox_item in result.scalars():
            kind = _torbox_kind(torbox_item.kind)
            if kind is not None:
                items[(kind, torbox_item.external_id)] = BackingProviderItem(
                    kind=kind,
                    item_id=torbox_item.external_id,
                )
        return tuple(items.values())


def _torbox_kind(kind: str) -> DownloadKind | None:
    return kind if kind in DOWNLOAD_KINDS else None
