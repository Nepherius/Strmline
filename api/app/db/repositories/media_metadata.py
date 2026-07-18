from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GeneratedFile, LibraryEntry, MediaExternalIdentity, MediaItem
from app.db.repositories.media_identity import MediaIdentityRepository

ENTRY_PATH_PARTS = 2
LIKE_ESCAPE = "\\"


@dataclass(frozen=True, slots=True)
class LibraryMediaRecord:
    media_item: MediaItem
    tmdb_identity: MediaExternalIdentity | None

    @property
    def tmdb_id(self) -> str | None:
        return self.tmdb_identity.external_id if self.tmdb_identity is not None else None


@dataclass(frozen=True, slots=True)
class LibraryMediaLocation:
    media_item_id: int
    category: str
    relative_prefix: str
    title: str


class MediaMetadataRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_for_library_prefix(self, relative_prefix: str) -> LibraryMediaRecord | None:
        result = await self._session.execute(
            self._library_record_query().where(_path_matches_prefix(relative_prefix))
        )
        return _unique_library_record([tuple(row) for row in result.all()])

    async def find_for_media_item(self, media_item_id: int) -> LibraryMediaRecord | None:
        result = await self._session.execute(
            self._library_record_query().where(MediaItem.id == media_item_id)
        )
        return _unique_library_record([tuple(row) for row in result.all()])

    async def location_for_media_item(
        self,
        media_item_id: int,
    ) -> LibraryMediaLocation | None:
        result = await self._session.execute(
            select(GeneratedFile.relative_path)
            .join(LibraryEntry)
            .where(LibraryEntry.media_item_id == media_item_id)
        )
        prefixes = {
            prefix for path in result.scalars() if (prefix := _entry_prefix(str(path))) is not None
        }
        if len(prefixes) != 1:
            return None
        relative_prefix = next(iter(prefixes))
        category, title = relative_prefix.split("/", maxsplit=1)
        if category not in {"movies", "shows", "anime"}:
            return None
        return LibraryMediaLocation(
            media_item_id=media_item_id,
            category=category,
            relative_prefix=relative_prefix,
            title=title,
        )

    async def records_for_library_prefixes(
        self,
        relative_prefixes: set[str],
    ) -> dict[str, LibraryMediaRecord]:
        if not relative_prefixes:
            return {}
        result = await self._session.execute(self._library_record_query())
        records: dict[str, dict[int, LibraryMediaRecord]] = {}
        for media_item, external_identity, generated_path in result.all():
            prefix = _entry_prefix(str(generated_path))
            if prefix is None or prefix not in relative_prefixes:
                continue
            records.setdefault(prefix, {})[media_item.id] = LibraryMediaRecord(
                media_item=media_item,
                tmdb_identity=external_identity,
            )
        return {
            prefix: next(iter(group.values()))
            for prefix, group in records.items()
            if len(group) == 1
        }

    async def tmdb_ids_for_library_prefixes(
        self,
        relative_prefixes: set[str],
    ) -> dict[str, str]:
        records = await self.records_for_library_prefixes(relative_prefixes)
        return {
            prefix: record.tmdb_id
            for prefix, record in records.items()
            if record.tmdb_id is not None
        }

    async def set_tmdb_id_for_media_item(
        self,
        media_item_id: int,
        tmdb_id: str,
    ) -> LibraryMediaRecord | None:
        record = await self.find_for_media_item(media_item_id)
        if record is None:
            return None
        identity_repository = MediaIdentityRepository(self._session)
        media_item = await identity_repository.set_manual_tmdb_identity(
            record.media_item,
            tmdb_id,
        )
        identity = await identity_repository.tmdb_identity_for_media(media_item.id)
        return LibraryMediaRecord(media_item=media_item, tmdb_identity=identity)

    async def set_tmdb_id_for_library_prefix(
        self,
        relative_prefix: str,
        tmdb_id: str,
    ) -> LibraryMediaRecord | None:
        record = await self.find_for_library_prefix(relative_prefix)
        if record is None:
            return None
        return await self.set_tmdb_id_for_media_item(record.media_item.id, tmdb_id)

    @staticmethod
    def _library_record_query():  # noqa: ANN205
        return (
            select(MediaItem, MediaExternalIdentity, GeneratedFile.relative_path)
            .select_from(GeneratedFile)
            .join(LibraryEntry)
            .join(MediaItem)
            .outerjoin(
                MediaExternalIdentity,
                (MediaExternalIdentity.media_item_id == MediaItem.id)
                & (MediaExternalIdentity.provider == "tmdb"),
            )
        )


def _path_matches_prefix(relative_prefix: str):  # noqa: ANN202
    escaped = escape_like(relative_prefix)
    return or_(
        GeneratedFile.relative_path == relative_prefix,
        GeneratedFile.relative_path.like(f"{escaped}/%", escape=LIKE_ESCAPE),
    )


def escape_like(value: str) -> str:
    return (
        value.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", f"{LIKE_ESCAPE}%")
        .replace("_", f"{LIKE_ESCAPE}_")
    )


def _entry_prefix(relative_path: str) -> str | None:
    relative = Path(relative_path)
    if len(relative.parts) < ENTRY_PATH_PARTS:
        return None
    return "/".join(relative.parts[:ENTRY_PATH_PARTS])


def _unique_library_record(rows: list[tuple[object, ...]]) -> LibraryMediaRecord | None:
    records: dict[int, LibraryMediaRecord] = {}
    for media_item, external_identity, _generated_path in rows:
        if not isinstance(media_item, MediaItem):
            continue
        records[media_item.id] = LibraryMediaRecord(
            media_item=media_item,
            tmdb_identity=(
                external_identity if isinstance(external_identity, MediaExternalIdentity) else None
            ),
        )
    return next(iter(records.values())) if len(records) == 1 else None
