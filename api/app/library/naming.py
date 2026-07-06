from __future__ import annotations

import re
from pathlib import PurePath

from app.library.entries import LibraryCategory, LibraryEntry

SEASON_EPISODE = re.compile(
    r"(?i)(?:^|[\s._-])s(?P<season>\d{1,2})[\s._-]*e(?P<episode>\d{1,3})(?:\D|$)"
)
FOLDER_SEASON = re.compile(r"(?i)\bseason[\s._-]*(?P<season>\d{1,2})\b")
LEADING_EPISODE = re.compile(r"(?i)^(?:episode[\s._-]*)?(?P<episode>\d{1,3})(?:\D|$)")
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
LEADING_RELEASE_GROUPS = re.compile(r"^(?:\[[^\]]{1,24}]\s*)+")


def library_entry_from_file_name(
    file_name: str, playback_url: str, folder_name: str = ""
) -> LibraryEntry:
    cleaned_name = _clean_release_name(PurePath(file_name).stem)
    season_episode = SEASON_EPISODE.search(cleaned_name)
    folder_episode = _folder_episode(cleaned_name, folder_name, season_episode)
    category = _category(
        cleaned_name,
        folder_name,
        has_episode=season_episode is not None or folder_episode is not None,
    )
    file_year = _year(cleaned_name)
    title, _ = _title(
        cleaned_name,
        folder_name,
        season_episode,
        file_year,
        use_folder_title=folder_episode is not None,
    )
    year = file_year or _year_from_folder(folder_name)

    if season_episode is None and folder_episode is None:
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
        season_number=_season_number(season_episode, folder_episode),
        episode_number=_episode_number(season_episode, folder_episode),
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
    *,
    use_folder_title: bool = False,
) -> tuple[str, bool]:
    if use_folder_title:
        fallback = _title_from_folder(folder_name)
        return fallback or "Unknown", True

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
        return title, False

    fallback = _title_from_folder(folder_name)
    return fallback or "Unknown", True


def _folder_episode(
    name: str,
    folder_name: str,
    season_episode: re.Match[str] | None,
) -> tuple[int, int] | None:
    if season_episode is not None:
        return None
    folder_season = FOLDER_SEASON.search(_clean_release_name(PurePath(folder_name).name))
    leading_episode = LEADING_EPISODE.search(name)
    if folder_season is None or leading_episode is None:
        return None
    return int(folder_season.group("season")), int(leading_episode.group("episode"))


def _season_number(
    season_episode: re.Match[str] | None,
    folder_episode: tuple[int, int] | None,
) -> int:
    if season_episode is not None:
        return int(season_episode.group("season"))
    if folder_episode is not None:
        return folder_episode[0]
    msg = "Series entries require season numbers."
    raise ValueError(msg)


def _episode_number(
    season_episode: re.Match[str] | None,
    folder_episode: tuple[int, int] | None,
) -> int:
    if season_episode is not None:
        return int(season_episode.group("episode"))
    if folder_episode is not None:
        return folder_episode[1]
    msg = "Series entries require episode numbers."
    raise ValueError(msg)


def _title_from_folder(folder_name: str) -> str:
    if not folder_name:
        return ""
    cleaned = _clean_release_name(PurePath(folder_name).name)
    season_episode = SEASON_EPISODE.search(cleaned)
    if season_episode is not None:
        cleaned = cleaned[: season_episode.start()]
    else:
        year_match = YEAR.search(cleaned)
        if year_match is not None:
            cleaned = cleaned[: year_match.start("year")]
    cleaned = TRAILING_QUALITY.sub("", cleaned)
    return _humanize_title(cleaned)


def _year(name: str) -> int | None:
    year_match = YEAR.search(name)
    if year_match is None:
        return None
    return int(year_match.group("year"))


def _year_from_folder(folder_name: str) -> int | None:
    if not folder_name:
        return None
    cleaned = _clean_release_name(PurePath(folder_name).name)
    return _year(cleaned)


def _clean_release_name(value: str) -> str:
    value = LEADING_RELEASE_GROUPS.sub("", value).strip()
    cleaned = value.replace("[", " ").replace("]", " ")
    cleaned = cleaned.replace("(", " ").replace(")", " ")
    return re.sub(r"\s+", " ", cleaned).strip()


def _humanize_title(value: str) -> str:
    title = re.sub(r"[._-]+", " ", value)
    title = re.sub(r"\s+", " ", title)
    return title.strip(" .-_")
