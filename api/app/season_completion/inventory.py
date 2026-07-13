from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LibraryEntry, MediaItem
from app.season_completion.ranking import EpisodeRef

SourceFileKey = tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class LibraryShow:
    media_item_id: int
    tmdb_id: str | None
    title: str
    episodes: frozenset[EpisodeRef]
    filenames_by_season: dict[int, tuple[str, ...]]


class SeasonInventoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def shows(self, filenames: dict[SourceFileKey, str]) -> tuple[LibraryShow, ...]:
        result = await self._session.execute(
            select(MediaItem, LibraryEntry)
            .join(LibraryEntry, LibraryEntry.media_item_id == MediaItem.id)
            .where(
                LibraryEntry.category.in_(("shows", "anime")),
                LibraryEntry.season_number.is_not(None),
                LibraryEntry.episode_number.is_not(None),
            )
            .order_by(MediaItem.id, LibraryEntry.season_number, LibraryEntry.episode_number)
        )
        grouped: dict[int, list[tuple[MediaItem, LibraryEntry]]] = defaultdict(list)
        for media_item, entry in result.all():
            grouped[media_item.id].append((media_item, entry))

        shows = (library_show(rows, filenames) for _, rows in sorted(grouped.items()) if rows)
        return tuple(show for show in shows if show.episodes)


def source_filename_index(
    downloads_by_kind: dict[str, list[dict[str, Any]]],
) -> dict[SourceFileKey, str]:
    index: dict[SourceFileKey, str] = {}
    for kind, downloads in downloads_by_kind.items():
        for item in downloads:
            item_id = _identifier(item.get("id"))
            raw_files = item.get("files")
            if item_id is None or not isinstance(raw_files, list):
                continue
            for raw_file in cast(list[object], raw_files):
                if not isinstance(raw_file, dict):
                    continue
                file_data = cast(dict[str, Any], raw_file)
                file_id = _identifier(file_data.get("id"))
                filename = _filename(file_data)
                if file_id is not None and filename is not None:
                    index[(kind, item_id, file_id)] = filename
    return index


def library_show(
    rows: list[tuple[MediaItem, LibraryEntry]],
    filenames: dict[SourceFileKey, str],
) -> LibraryShow:
    media_item = rows[0][0]
    episodes: set[EpisodeRef] = set()
    by_season: dict[int, list[str]] = defaultdict(list)
    for _, entry in rows:
        if entry.season_number is None or entry.episode_number is None:
            continue
        filename = filenames.get((entry.provider, entry.provider_item_id, entry.provider_file_id))
        if filename is None:
            continue
        episodes.add(EpisodeRef(entry.season_number, entry.episode_number))
        by_season[entry.season_number].append(filename)
    return LibraryShow(
        media_item_id=media_item.id,
        tmdb_id=media_item.tmdb_id,
        title=media_item.title,
        episodes=frozenset(episodes),
        filenames_by_season={season: tuple(values) for season, values in by_season.items()},
    )


def _identifier(value: object) -> str | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _filename(raw_file: dict[str, Any]) -> str | None:
    for key in ("short_name", "name", "filename"):
        value = raw_file.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().replace("\\", "/").rsplit("/", maxsplit=1)[-1]
    return None
