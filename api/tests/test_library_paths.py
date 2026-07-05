from pathlib import Path

import pytest

from app.library.entries import LibraryEntry
from app.library.paths import (
    clean_path_segment,
    ensure_within_root,
    library_entry_relative_path,
)


def test_clean_path_segment_removes_unsafe_characters():
    assert clean_path_segment('../Bad: Movie? * "Name"') == "Bad Movie Name"


def test_clean_path_segment_uses_fallback_for_empty_values():
    assert clean_path_segment("...") == "Unknown"


def test_movie_entry_path_uses_movie_folder():
    entry = LibraryEntry(
        category="movies",
        title="Project Hail Mary",
        year=2026,
        resolver_url="http://strmline:8080/play/movie-id?token=secret",
    )

    assert library_entry_relative_path(entry) == Path(
        "movies",
        "Project Hail Mary (2026)",
        "Project Hail Mary (2026).strm",
    )


def test_show_entry_path_uses_season_episode_folder():
    entry = LibraryEntry(
        category="shows",
        title="Slow Horses",
        year=2022,
        season_number=1,
        episode_number=2,
        resolver_url="http://strmline:8080/play/show-id?token=secret",
    )

    assert library_entry_relative_path(entry) == Path(
        "shows",
        "Slow Horses (2022)",
        "Season 01",
        "Slow Horses - S01E02.strm",
    )


def test_anime_entry_path_uses_anime_category():
    entry = LibraryEntry(
        category="anime",
        title="Frieren Beyond Journey's End",
        season_number=1,
        episode_number=1,
        resolver_url="http://strmline:8080/play/anime-id?token=secret",
    )

    assert library_entry_relative_path(entry) == Path(
        "anime",
        "Frieren Beyond Journey's End",
        "Season 01",
        "Frieren Beyond Journey's End - S01E01.strm",
    )


def test_anime_movie_entry_path_uses_anime_movie_folder():
    entry = LibraryEntry(
        category="anime",
        title="Spirited Away",
        year=2001,
        resolver_url="http://strmline:8080/play/anime-movie-id?token=secret",
    )

    assert library_entry_relative_path(entry) == Path(
        "anime",
        "Spirited Away (2001)",
        "Spirited Away (2001).strm",
    )


def test_ensure_within_root_rejects_outside_path(tmp_path: Path):
    with pytest.raises(ValueError, match="outside"):
        _ = ensure_within_root(tmp_path, tmp_path.parent / "outside.strm")
