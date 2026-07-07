from __future__ import annotations

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ClassificationOverride
from app.library.classification_override import LibraryClassificationOverride
from app.library.entries import LibraryCategory


class ClassificationOverrideRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> tuple[LibraryClassificationOverride, ...]:
        result = await self._session.execute(
            select(ClassificationOverride).order_by(
                ClassificationOverride.source_prefix.asc(),
            )
        )
        return tuple(_override_record(row) for row in result.scalars())

    async def by_source_prefix(self) -> dict[str, LibraryClassificationOverride]:
        return {override.source_prefix: override for override in await self.list_all()}

    async def upsert(
        self,
        *,
        source_category: LibraryCategory,
        source_prefix: str,
        title: str,
        target_category: LibraryCategory,
    ) -> LibraryClassificationOverride:
        result = await self._session.execute(
            select(ClassificationOverride).where(
                ClassificationOverride.source_prefix == source_prefix
            )
        )
        override = result.scalar_one_or_none()
        if override is None:
            override = ClassificationOverride(
                source_category=source_category,
                source_prefix=source_prefix,
                title=title,
                target_category=target_category,
            )
            self._session.add(override)
        else:
            override.source_category = source_category
            override.title = title
            override.target_category = target_category
        await self._session.flush()
        return _override_record(override)

    async def delete(self, source_prefix: str) -> bool:
        result = await self._session.execute(
            select(ClassificationOverride).where(
                ClassificationOverride.source_prefix == source_prefix
            )
        )
        override = result.scalar_one_or_none()
        if override is None:
            return False
        await self._session.delete(override)
        await self._session.flush()
        return True


def _override_record(row: ClassificationOverride) -> LibraryClassificationOverride:
    return LibraryClassificationOverride(
        source_category=_category(row.source_category),
        source_prefix=row.source_prefix,
        title=row.title,
        target_category=_category(row.target_category),
    )


def _category(value: str) -> LibraryCategory:
    if value in {"movies", "shows", "anime"}:
        return cast(LibraryCategory, value)
    msg = f"Invalid library category: {value}"
    raise ValueError(msg)
