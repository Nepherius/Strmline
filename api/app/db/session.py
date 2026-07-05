from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


def require_database_url() -> str:
    database_url = get_settings().database_url
    if database_url is None:
        message = "STRMLINE_DATABASE_URL or STRMLINE_POSTGRES_HOST and STRMLINE_POSTGRES_PASSWORD must be configured before using the database."
        raise RuntimeError(message)
    return normalize_async_database_url(database_url)


def normalize_async_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return database_url


def build_async_engine(database_url: str | None = None) -> AsyncEngine:
    return create_async_engine(
        normalize_async_database_url(database_url)
        if database_url is not None
        else require_database_url(),
        pool_pre_ping=True,
    )


def build_session_factory(
    database_url: str | None = None,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        build_async_engine(database_url),
        expire_on_commit=False,
    )
