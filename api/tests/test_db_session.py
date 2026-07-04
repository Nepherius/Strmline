import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.config import get_settings
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


def test_build_session_factory_uses_async_engine() -> None:
    session_factory = build_session_factory(
        "postgresql+asyncpg://user:pass@localhost/db",
    )

    assert isinstance(session_factory, async_sessionmaker)
