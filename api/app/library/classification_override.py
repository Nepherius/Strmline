from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.library.entries import LibraryCategory, LibraryEntry
from app.library.paths import library_entry_relative_path

PREFIX_PARTS = 2


@dataclass(frozen=True, slots=True)
class LibraryClassificationOverride:
    source_category: LibraryCategory
    source_prefix: str
    title: str
    target_category: LibraryCategory


def target_prefix_for_override(override: LibraryClassificationOverride) -> str:
    parts = Path(override.source_prefix).parts
    if len(parts) >= PREFIX_PARTS:
        return Path(override.target_category, *parts[1:]).as_posix()
    return Path(override.target_category, override.title).as_posix()


def source_prefix_for_entry(entry: LibraryEntry) -> str:
    parts = library_entry_relative_path(entry).parts
    if len(parts) >= PREFIX_PARTS:
        return Path(parts[0], parts[1]).as_posix()
    return library_entry_relative_path(entry).as_posix()


def apply_classification_override(
    entry: LibraryEntry,
    override: LibraryClassificationOverride | None,
) -> LibraryEntry:
    if override is None or override.source_category != entry.category:
        return entry
    if override.target_category == entry.category:
        return entry
    if not _can_apply_target(entry, override.target_category):
        return entry
    return LibraryEntry(
        category=override.target_category,
        title=entry.title,
        year=entry.year,
        season_number=entry.season_number,
        episode_number=entry.episode_number,
        resolver_url=entry.resolver_url,
    )


def _can_apply_target(entry: LibraryEntry, target_category: LibraryCategory) -> bool:
    is_episode = entry.season_number is not None or entry.episode_number is not None
    if target_category == "movies":
        return not is_episode
    if target_category == "shows":
        return is_episode
    return True
