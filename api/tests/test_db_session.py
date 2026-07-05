from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.config import Settings, get_settings
from app.db.session import (
    build_async_engine,
    build_session_factory,
    normalize_async_database_url,
    require_database_url,
)


def test_normalize_async_database_url_accepts_common_postgres_scheme() -> None:
    assert normalize_async_database_url("postgresql://user:pass@localhost/db") == (
        "postgresql+asyncpg://user:pass@localhost/db"
    )


def test_require_database_url_reports_missing_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STRMLINE_DATABASE_URL", raising=False)
    monkeypatch.delenv("STRMLINE_POSTGRES_HOST", raising=False)
    monkeypatch.delenv("STRMLINE_POSTGRES_PASSWORD", raising=False)
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="STRMLINE_DATABASE_URL"):
        _ = require_database_url()

    get_settings.cache_clear()


def test_build_async_engine_from_configured_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRMLINE_DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/db")
    get_settings.cache_clear()

    engine = build_async_engine()

    get_settings.cache_clear()
    assert isinstance(engine, AsyncEngine)
    assert engine.url.render_as_string(hide_password=True) == (
        "postgresql+asyncpg://user:***@localhost/db"
    )


def test_settings_can_build_database_url_from_postgres_parts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STRMLINE_DATABASE_URL", raising=False)
    monkeypatch.setenv("STRMLINE_POSTGRES_HOST", "postgres")
    monkeypatch.setenv("STRMLINE_POSTGRES_PORT", "5432")
    monkeypatch.setenv("STRMLINE_POSTGRES_DATABASE", "strmline")
    monkeypatch.setenv("STRMLINE_POSTGRES_USER", "strmline")
    monkeypatch.setenv("STRMLINE_POSTGRES_PASSWORD", "secret with @")
    get_settings.cache_clear()

    database_url = require_database_url()

    get_settings.cache_clear()
    assert database_url == "postgresql+asyncpg://strmline:secret+with+%40@postgres:5432/strmline"


def test_settings_do_not_load_dotenv_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dotenv_path = tmp_path / ".env"
    _ = dotenv_path.write_text("STRMLINE_DATABASE_URL=postgresql://dotenv/db\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("STRMLINE_DATABASE_URL", raising=False)

    assert Settings().database_url is None


def test_build_session_factory_uses_async_engine() -> None:
    session_factory = build_session_factory(
        "postgresql+asyncpg://user:pass@localhost/db",
    )

    assert isinstance(session_factory, async_sessionmaker)
