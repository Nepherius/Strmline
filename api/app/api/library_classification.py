from typing import cast

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.library_identity import require_media_location
from app.db.repositories.classification_override import ClassificationOverrideRepository
from app.library.classification_override import LibraryClassificationOverride
from app.library.entries import LibraryCategory


async def save_media_classification(
    session: AsyncSession,
    *,
    media_item_id: int,
    target_category: str,
) -> LibraryClassificationOverride:
    location = await require_media_location(session, media_item_id)
    repository = ClassificationOverrideRepository(session)
    existing = await repository.for_current_prefix(location.relative_prefix)
    source_category = existing.source_category if existing else _category(location.category)
    if target_category == source_category:
        raise HTTPException(status_code=400, detail="Target category must be different.")
    return await repository.upsert(
        source_category=source_category,
        source_prefix=existing.source_prefix if existing else location.relative_prefix,
        title=existing.title if existing else location.title,
        target_category=_category(target_category),
    )


async def delete_media_classification(session: AsyncSession, media_item_id: int) -> None:
    location = await require_media_location(session, media_item_id)
    repository = ClassificationOverrideRepository(session)
    override = await repository.for_current_prefix(location.relative_prefix)
    if override is not None:
        _ = await repository.delete(override.source_prefix)


def _category(value: str) -> LibraryCategory:
    if value in {"movies", "shows", "anime"}:
        return cast(LibraryCategory, value)
    raise HTTPException(status_code=400, detail="Library category is invalid.")
