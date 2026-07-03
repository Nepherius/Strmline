from pathlib import Path

from app.library.summary import summarize_library


def test_summarize_library_counts_categories_and_files(tmp_path: Path) -> None:
    _write_strm(tmp_path / "movies" / "Movie One (2024)" / "Movie One (2024).strm")
    _write_strm(tmp_path / "shows" / "Show One" / "Season 01" / "Show One - S01E01.strm")
    _write_strm(tmp_path / "anime" / "Anime One" / "Season 01" / "Anime One - S01E01.strm")

    summary = summarize_library(tmp_path)

    assert summary.exists is True
    assert summary.total_files == 3
    assert summary.category_counts == {"movies": 1, "shows": 1, "anime": 1}
    assert [file.relative_path for file in summary.files] == [
        "movies/Movie One (2024)/Movie One (2024).strm",
        "shows/Show One/Season 01/Show One - S01E01.strm",
        "anime/Anime One/Season 01/Anime One - S01E01.strm",
    ]


def test_summarize_library_groups_duplicate_titles(tmp_path: Path) -> None:
    _write_strm(tmp_path / "movies" / "Same Movie (2024)" / "Same Movie (2024).strm")
    _write_strm(tmp_path / "movies" / "Same.Movie.2024" / "Same Movie 2024.strm")

    summary = summarize_library(tmp_path)

    assert len(summary.duplicate_groups) == 1
    assert summary.duplicate_groups[0].key == "movies:same movie 2024"
    assert len(summary.duplicate_groups[0].files) == 2


def test_summarize_library_does_not_group_distinct_show_episodes(tmp_path: Path) -> None:
    _write_strm(tmp_path / "shows" / "Same Show" / "Season 01" / "Same Show - S01E01.strm")
    _write_strm(tmp_path / "shows" / "Same Show" / "Season 01" / "Same Show - S01E02.strm")

    summary = summarize_library(tmp_path)

    assert summary.duplicate_groups == ()


def test_summarize_library_handles_missing_root(tmp_path: Path) -> None:
    summary = summarize_library(tmp_path / "missing")

    assert summary.exists is False
    assert summary.total_files == 0
    assert summary.files == ()


def _write_strm(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text("https://example.test/video\n", encoding="utf-8")
