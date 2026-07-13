from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LibraryEntry, MediaItem, TorBoxStoredFile
from app.season_completion.ranking import EpisodeRef


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

    async def shows(self) -> tuple[LibraryShow, ...]:
        result = await self._session.execute(
            select(MediaItem, LibraryEntry, TorBoxStoredFile)
            .join(LibraryEntry, LibraryEntry.media_item_id == MediaItem.id)
            .join(TorBoxStoredFile, LibraryEntry.torbox_file_id == TorBoxStoredFile.id)
            .where(
                LibraryEntry.category.in_(("shows", "anime")),
                LibraryEntry.season_number.is_not(None),
                LibraryEntry.episode_number.is_not(None),
            )
            .order_by(MediaItem.id, LibraryEntry.season_number, LibraryEntry.episode_number)
        )
        grouped: dict[int, list[tuple[MediaItem, LibraryEntry, TorBoxStoredFile]]] = defaultdict(
            list
        )
        for media_item, entry, torbox_file in result.all():
            grouped[media_item.id].append((media_item, entry, torbox_file))

        shows = (library_show(rows) for _, rows in sorted(grouped.items()) if rows)
        return tuple(show for show in shows if show.episodes)


def library_show(
    rows: list[tuple[MediaItem, LibraryEntry, TorBoxStoredFile]],
) -> LibraryShow:
    media_item = rows[0][0]
    episodes: set[EpisodeRef] = set()
    by_season: dict[int, list[str]] = defaultdict(list)
    for _, entry, torbox_file in rows:
        if entry.season_number is None or entry.episode_number is None:
            continue
        episodes.add(EpisodeRef(entry.season_number, entry.episode_number))
        by_season[entry.season_number].append(torbox_file.file_name)
    return LibraryShow(
        media_item_id=media_item.id,
        tmdb_id=media_item.tmdb_id,
        title=media_item.title,
        episodes=frozenset(episodes),
        filenames_by_season={season: tuple(values) for season, values in by_season.items()},
    )
