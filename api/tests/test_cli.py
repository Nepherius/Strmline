from pathlib import Path

import pytest

from app.cli import main, positive_int
from app.core.config import get_settings


def test_sync_torbox_strm_requires_resolver_settings_without_direct_url_flag(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["sync-torbox-strm"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "STRMLINE_TORBOX_API_KEY" in captured.err


def test_positive_int_rejects_zero() -> None:
    with pytest.raises(ValueError, match="positive"):
        _ = positive_int("0")


def test_sync_torbox_strm_direct_playback_mode_skips_resolver_requirement(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRMLINE_TORBOX_API_KEY", "torbox-secret")
    monkeypatch.setenv("STRMLINE_PLAYBACK_MODE", "direct")
    get_settings.cache_clear()

    exit_code = main(["sync-torbox-strm"])

    get_settings.cache_clear()
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "STRMLINE_LIBRARY_ROOT" in captured.err
    assert "Resolver mode requires" not in captured.err


def test_validate_jellyfin_library_reports_ready(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    root = tmp_path / "library"
    strm_file = root / "movies" / "Movie Name (2024)" / "Movie Name (2024).strm"
    strm_file.parent.mkdir(parents=True)
    _ = strm_file.write_text("http://127.0.0.1:8001/play/movie?token=secret\n", encoding="utf-8")

    exit_code = main(["validate-jellyfin-library", "--library-root", str(root)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Status: ready" in captured.out
    assert "Total STRM files: 1" in captured.out


def test_validate_jellyfin_library_returns_failure_for_bad_library(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    root = tmp_path / "library"
    strm_file = root / "other" / "Loose.strm"
    strm_file.parent.mkdir(parents=True)
    _ = strm_file.write_text("http://127.0.0.1:8001/play/loose?token=secret\n", encoding="utf-8")

    exit_code = main(["validate-jellyfin-library", "--library-root", str(root)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Status: needs attention" in captured.out
    assert "[strm_outside_category]" in captured.out
