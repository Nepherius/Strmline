from __future__ import annotations

import re
from pathlib import Path

from app.library.entries import LibraryEntry

INVALID_SEGMENT_CHARS = re.compile(r"[\/\\:\*\?\"<>\|\x00-\x1f]")
WHITESPACE = re.compile(r"\s+")


def clean_path_segment(value: str | None, fallback: str = "Unknown") -> str:
    if value is None:
        return fallback

    cleaned = INVALID_SEGMENT_CHARS.sub(" ", value)
    cleaned = cleaned.replace("..", " ")
    cleaned = WHITESPACE.sub(" ", cleaned)
    cleaned = cleaned.strip(" .")
    return cleaned or fallback


def title_year(title: str, year: int | None) -> str:
    clean_title = clean_path_segment(title)
    if year is None:
        return clean_title
    return f"{clean_title} ({year})"


def season_folder(season_number: int) -> str:
    return f"Season {season_number:02}"


def episode_suffix(season_number: int, episode_number: int) -> str:
    return f"S{season_number:02}E{episode_number:02}"


def library_entry_relative_path(entry: LibraryEntry) -> Path:
    if entry.category == "movies" or (
        entry.category == "anime" and entry.season_number is None and entry.episode_number is None
    ):
        root_folder = title_year(entry.title, entry.year)
        file_name = f"{root_folder}.strm"
        return Path(entry.category, root_folder, file_name)

    if entry.season_number is None or entry.episode_number is None:
        msg = "Series entries require season and episode numbers."
        raise ValueError(msg)

    clean_title = clean_path_segment(entry.title)
    root_folder = clean_title
    file_name = f"{clean_title} - {episode_suffix(entry.season_number, entry.episode_number)}.strm"
    return Path(
        entry.category,
        root_folder,
        season_folder(entry.season_number),
        file_name,
    )


def ensure_within_root(root: Path, target: Path) -> Path:
    resolved_root = root.resolve(strict=False)
    resolved_target = target.resolve(strict=False)

    try:
        _ = resolved_target.relative_to(resolved_root)
    except ValueError as error:
        msg = f"Target path is outside library root: {target}"
        raise ValueError(msg) from error

    return resolved_target
