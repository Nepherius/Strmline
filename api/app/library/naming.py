from __future__ import annotations

import re
from pathlib import PurePath

from app.library.entries import LibraryCategory, LibraryEntry

SEASON_EPISODE = re.compile(r"(?i)(?:^|[\s._-])s(?P<season>\d{1,2})e(?P<episode>\d{1,3})(?:\D|$)")
YEAR = re.compile(r"(?:^|[^\d])(?P<year>(?:19|20)\d{2})(?:[^\d]|$)")
QUALITY_TERMS = (
    "2160p",
    "1080p",
    "720p",
    "480p",
    r"web[-_. ]?dl",
    "webrip",
    "bluray",
    "brrip",
    "hdtv",
    "hdrip",
    "x264",
    "x265",
    "h264",
    "h265",
    "hevc",
    "10bit",
    "aac",
    "dts",
    "atmos",
    "remux",
    "proper",
    "repack",
)
TRAILING_QUALITY = re.compile(rf"(?i)\b({'|'.join(QUALITY_TERMS)})\b.*$")


def library_entry_from_file_name(
    file_name: str, playback_url: str, folder_name: str = ""
) -> LibraryEntry:
    cleaned_name = _clean_release_name(PurePath(file_name).stem)
    season_episode = SEASON_EPISODE.search(cleaned_name)
    category = _category(cleaned_name, folder_name, has_episode=season_episode is not None)
    year = _year(cleaned_name)
    title = _title(cleaned_name, folder_name, season_episode, year)

    if season_episode is None:
        return LibraryEntry(
            category="movies",
            title=title,
            year=year,
            resolver_url=playback_url,
        )

    return LibraryEntry(
        category=category,
        title=title,
        year=year,
        season_number=int(season_episode.group("season")),
        episode_number=int(season_episode.group("episode")),
        resolver_url=playback_url,
    )


def _category(name: str, folder_name: str, *, has_episode: bool) -> LibraryCategory:
    source = f"{folder_name} {name}".casefold()
    if "anime" in source:
        return "anime"
    if has_episode:
        return "shows"
    return "movies"


def _title(
    name: str,
    folder_name: str,
    season_episode: re.Match[str] | None,
    year: int | None,
) -> str:
    title_source = name
    if season_episode is not None:
        title_source = name[: season_episode.start()]
    elif year is not None:
        year_match = YEAR.search(name)
        if year_match is not None:
            title_source = name[: year_match.start("year")]

    title_source = TRAILING_QUALITY.sub("", title_source)
    title = _humanize_title(title_source)
    if title:
        return title

    fallback = _humanize_title(PurePath(folder_name).name)
    return fallback or "Unknown"


def _year(name: str) -> int | None:
    year_match = YEAR.search(name)
    if year_match is None:
        return None
    return int(year_match.group("year"))


def _clean_release_name(value: str) -> str:
    cleaned = value.replace("[", " ").replace("]", " ")
    cleaned = cleaned.replace("(", " ").replace(")", " ")
    return re.sub(r"\s+", " ", cleaned).strip()


def _humanize_title(value: str) -> str:
    title = re.sub(r"[._-]+", " ", value)
    title = re.sub(r"\s+", " ", title)
    return title.strip(" .-_")
