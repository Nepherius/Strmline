from pathlib import Path

from app.library.validation import validate_jellyfin_library


def test_validate_jellyfin_library_accepts_expected_layout(tmp_path: Path) -> None:
    _write_strm(
        tmp_path / "movies" / "Movie Name (2024)" / "Movie Name (2024).strm",
        "http://127.0.0.1:8001/play/movie?token=secret",
    )
    _write_strm(
        tmp_path / "shows" / "Show Name (2024)" / "Season 01" / "Show Name - S01E01.strm",
        "http://127.0.0.1:8001/play/show?token=secret",
    )
    _write_strm(
        tmp_path / "anime" / "Anime Movie (2001)" / "Anime Movie (2001).strm",
        "http://127.0.0.1:8001/play/anime-movie?token=secret",
    )
    _write_strm(
        tmp_path / "anime" / "Anime Show" / "Season 01" / "Anime Show - S01E01.strm",
        "http://127.0.0.1:8001/play/anime-show?token=secret",
    )

    report = validate_jellyfin_library(tmp_path)

    assert report.ok is True
    assert report.summary.total_files == 4
    assert report.summary.category_counts == {"movies": 1, "shows": 1, "anime": 2}
    assert report.errors == ()


def test_validate_jellyfin_library_rejects_bad_strm_url(tmp_path: Path) -> None:
    _write_strm(
        tmp_path / "movies" / "Movie Name (2024)" / "Movie Name (2024).strm",
        "/local/file.mkv",
    )

    report = validate_jellyfin_library(tmp_path)

    assert report.ok is False
    assert report.errors[0].code == "strm_url_invalid"


def test_validate_jellyfin_library_rejects_show_without_season_folder(tmp_path: Path) -> None:
    _write_strm(
        tmp_path / "shows" / "Show Name (2024)" / "Show Name - S01E01.strm",
        "http://127.0.0.1:8001/play/show?token=secret",
    )

    report = validate_jellyfin_library(tmp_path)

    assert report.ok is False
    assert report.errors[0].code == "series_path_shape"


def test_validate_jellyfin_library_rejects_strm_outside_categories(tmp_path: Path) -> None:
    _write_strm(
        tmp_path / "other" / "Loose.strm",
        "http://127.0.0.1:8001/play/loose?token=secret",
    )

    report = validate_jellyfin_library(tmp_path)

    assert report.ok is False
    assert report.errors[0].code == "strm_outside_category"


def test_validate_jellyfin_library_reports_missing_root(tmp_path: Path) -> None:
    report = validate_jellyfin_library(tmp_path / "missing")

    assert report.ok is False
    assert report.errors[0].code == "library_root_missing"


def _write_strm(path: Path, url: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(f"{url}\n", encoding="utf-8")
