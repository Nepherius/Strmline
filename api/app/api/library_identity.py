from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.media_metadata import (
    LibraryMediaLocation,
    LibraryMediaRecord,
    MediaMetadataRepository,
)


async def require_matching_media_record(
    session: AsyncSession,
    *,
    media_item_id: int,
    relative_prefix: str,
) -> LibraryMediaRecord:
    record = await MediaMetadataRepository(session).find_for_library_prefix(relative_prefix)
    if record is None or record.media_item.id != media_item_id:
        raise HTTPException(
            status_code=409,
            detail="Library entry identity no longer matches its current path.",
        )
    return record


async def require_media_location(
    session: AsyncSession,
    media_item_id: int,
) -> LibraryMediaLocation:
    location = await MediaMetadataRepository(session).location_for_media_item(media_item_id)
    if location is None:
        raise HTTPException(
            status_code=409,
            detail="Library entry has no unique current location.",
        )
    return location
