import pytest

from app.cli import main, positive_int


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
