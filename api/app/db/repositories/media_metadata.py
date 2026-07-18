from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.models import GeneratedFile, LibraryEntry, MediaExternalIdentity, MediaItem
from app.db.repositories.media_identity import MediaIdentityRepository

ENTRY_PATH_PARTS = 2
LIKE_ESCAPE = "\\"
LIBRARY_CATEGORIES = ("movies", "shows", "anime")
LibraryPageSort = Literal["title", "category", "relative_path"]
SortDirection = Literal["asc", "desc"]

__all__ = [
    "LibraryMediaLocation",
    "LibraryMediaPage",
    "LibraryMediaRecord",
    "LibraryPageEntry",
    "LibraryPageOptions",
    "MediaMetadataRepository",
    "escape_like",
]


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


@dataclass(frozen=True, slots=True)
class LibraryPageEntry:
    media_item_id: int
    title: str
    category: str
    relative_prefix: str
    file_count: int
    tmdb_id: str | None


@dataclass(frozen=True, slots=True)
class LibraryMediaPage:
    entries: tuple[LibraryPageEntry, ...]
    next_cursor: str | None
    total_matches: int | None
    total_files: int | None
    category_counts: dict[str, int] | None


@dataclass(frozen=True, slots=True)
class LibraryPageOptions:
    limit: int
    category: str | None
    query: str
    sort_key: LibraryPageSort
    direction: SortDirection
    include_overview: bool
    cursor: str | None


@dataclass(frozen=True, slots=True)
class _LibraryCursor:
    sort_key: LibraryPageSort
    direction: SortDirection
    sort_value: str
    media_item_id: int
    category: str
    scope: str


class MediaMetadataRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def library_page(
        self,
        options: LibraryPageOptions,
    ) -> LibraryMediaPage:
        category_counts: dict[str, int] | None = None
        total_files: int | None = None
        total_matches: int | None = None
        if options.include_overview:
            category_counts, total_files = await self._library_counts()
        first_path = func.min(GeneratedFile.relative_path).label("first_path")
        catalog_statement = (
            select(
                MediaItem.id.label("media_item_id"),
                MediaItem.title.label("title"),
                LibraryEntry.category.label("category"),
                func.count(GeneratedFile.id).label("file_count"),
                first_path,
                MediaExternalIdentity.external_id.label("tmdb_id"),
            )
            .select_from(LibraryEntry)
            .join(MediaItem, MediaItem.id == LibraryEntry.media_item_id)
            .join(GeneratedFile, GeneratedFile.library_entry_id == LibraryEntry.id)
            .outerjoin(
                MediaExternalIdentity,
                (MediaExternalIdentity.media_item_id == MediaItem.id)
                & (MediaExternalIdentity.provider == "tmdb"),
            )
            .group_by(MediaItem.id, MediaExternalIdentity.id, LibraryEntry.category)
        )
        if options.category is not None:
            catalog_statement = catalog_statement.where(LibraryEntry.category == options.category)
        if normalized_query := options.query.strip().casefold():
            catalog_statement = catalog_statement.where(_library_search_condition(normalized_query))
        catalog = catalog_statement.subquery()
        if options.include_overview:
            count_result = await self._session.execute(select(func.count()).select_from(catalog))
            total_matches = int(count_result.scalar_one())
        sort_expression = {
            "title": func.lower(catalog.c.title),
            "category": catalog.c.category,
            "relative_path": catalog.c.first_path,
        }[options.sort_key]
        statement = select(
            catalog.c.media_item_id,
            catalog.c.title,
            catalog.c.category,
            catalog.c.file_count,
            catalog.c.first_path,
            catalog.c.tmdb_id,
            sort_expression.label("sort_value"),
        ).select_from(catalog)
        if options.cursor is not None:
            cursor = _decode_library_cursor(options.cursor, options)
            primary_after = (
                sort_expression < cursor.sort_value
                if options.direction == "desc"
                else sort_expression > cursor.sort_value
            )
            tie_after = or_(
                catalog.c.media_item_id > cursor.media_item_id,
                (
                    (catalog.c.media_item_id == cursor.media_item_id)
                    & (catalog.c.category > cursor.category)
                ),
            )
            statement = statement.where(
                or_(
                    primary_after,
                    (sort_expression == cursor.sort_value) & tie_after,
                )
            )
        ordered = sort_expression.desc() if options.direction == "desc" else sort_expression.asc()
        result = await self._session.execute(
            statement.order_by(
                ordered,
                catalog.c.media_item_id.asc(),
                catalog.c.category.asc(),
            ).limit(options.limit + 1)
        )
        rows = [tuple(row) for row in result.all()]
        entries, next_cursor = _library_page_entries(rows, options)
        return LibraryMediaPage(
            entries=entries,
            next_cursor=next_cursor,
            total_matches=total_matches,
            total_files=total_files,
            category_counts=category_counts,
        )

    async def _library_counts(self) -> tuple[dict[str, int], int]:
        result = await self._session.execute(
            select(
                LibraryEntry.category,
                func.count(func.distinct(LibraryEntry.media_item_id)),
                func.count(GeneratedFile.id),
            )
            .select_from(LibraryEntry)
            .join(GeneratedFile, GeneratedFile.library_entry_id == LibraryEntry.id)
            .group_by(LibraryEntry.category)
        )
        category_counts: dict[str, int] = dict.fromkeys(LIBRARY_CATEGORIES, 0)
        total_files = 0
        for category, title_count, file_count in result.all():
            category_counts[str(category)] = int(title_count)
            total_files += int(file_count)
        return category_counts, total_files

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


def _library_search_condition(normalized_query: str):  # noqa: ANN202
    pattern = f"%{escape_like(normalized_query)}%"
    matching_entry = aliased(LibraryEntry)
    matching_file = aliased(GeneratedFile)
    path_matches = exists(
        select(1)
        .select_from(matching_entry)
        .join(matching_file, matching_file.library_entry_id == matching_entry.id)
        .where(
            matching_entry.media_item_id == MediaItem.id,
            matching_entry.category == LibraryEntry.category,
            func.lower(matching_file.relative_path).like(
                pattern,
                escape=LIKE_ESCAPE,
            ),
        )
    )
    return or_(
        func.lower(MediaItem.title).like(pattern, escape=LIKE_ESCAPE),
        path_matches,
    )


def _encode_library_cursor(cursor: _LibraryCursor) -> str:
    payload = json.dumps(
        {
            "v": 1,
            "sort_key": cursor.sort_key,
            "direction": cursor.direction,
            "sort_value": cursor.sort_value,
            "media_item_id": cursor.media_item_id,
            "category": cursor.category,
            "scope": cursor.scope,
        },
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _library_page_entries(
    rows: list[tuple[object, ...]],
    options: LibraryPageOptions,
) -> tuple[tuple[LibraryPageEntry, ...], str | None]:
    page_rows = rows[: options.limit]
    entries: list[LibraryPageEntry] = []
    for media_item_id, title, category, file_count, path, tmdb_id, _sort in page_rows:
        relative_prefix = _entry_prefix(str(path))
        if relative_prefix is None:
            continue
        entries.append(
            LibraryPageEntry(
                media_item_id=_database_int(media_item_id),
                title=str(title),
                category=str(category),
                relative_prefix=relative_prefix,
                file_count=_database_int(file_count),
                tmdb_id=str(tmdb_id) if tmdb_id is not None else None,
            )
        )
    if len(rows) <= options.limit or not page_rows:
        return tuple(entries), None
    last = page_rows[-1]
    next_cursor = _encode_library_cursor(
        _LibraryCursor(
            sort_key=options.sort_key,
            direction=options.direction,
            sort_value=str(last[6]),
            media_item_id=_database_int(last[0]),
            category=str(last[2]),
            scope=_library_cursor_scope(options),
        )
    )
    return tuple(entries), next_cursor


def _decode_library_cursor(
    value: str,
    options: LibraryPageOptions,
) -> _LibraryCursor:
    try:
        padding = "=" * (-len(value) % 4)
        payload = base64.b64decode(
            f"{value}{padding}",
            altchars=b"-_",
            validate=True,
        )
        decoded = json.loads(payload)
        return _validated_library_cursor(decoded, options)
    except (
        binascii.Error,
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        msg = "Library cursor is invalid or does not match the current filters and sort."
        raise ValueError(msg) from error


def _validated_library_cursor(
    decoded: object,
    options: LibraryPageOptions,
) -> _LibraryCursor:
    if not isinstance(decoded, dict):
        raise TypeError
    data = cast(dict[str, object], decoded)
    if data.get("v") != 1:
        raise ValueError
    sort_key = data["sort_key"]
    direction = data["direction"]
    sort_value = data["sort_value"]
    media_item_id = data["media_item_id"]
    category = data["category"]
    scope = data["scope"]
    if (
        sort_key not in {"title", "category", "relative_path"}
        or direction not in {"asc", "desc"}
        or not isinstance(sort_value, str)
        or not isinstance(media_item_id, int)
        or isinstance(media_item_id, bool)
        or media_item_id < 1
        or not isinstance(category, str)
        or category not in LIBRARY_CATEGORIES
        or not isinstance(scope, str)
        or scope != _library_cursor_scope(options)
        or sort_key != options.sort_key
        or direction != options.direction
    ):
        raise ValueError
    return _LibraryCursor(
        sort_key=cast(LibraryPageSort, sort_key),
        direction=cast(SortDirection, direction),
        sort_value=sort_value,
        media_item_id=media_item_id,
        category=category,
        scope=scope,
    )


def _library_cursor_scope(options: LibraryPageOptions) -> str:
    value = json.dumps(
        {
            "category": options.category,
            "query": options.query.strip().casefold(),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(value).hexdigest()


def _database_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        msg = "Library query returned a non-integer identifier or count."
        raise TypeError(msg)
    return value


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
