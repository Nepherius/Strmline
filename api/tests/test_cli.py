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
