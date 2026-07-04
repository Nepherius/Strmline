from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.db.session import build_session_factory


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return build_session_factory()


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async_session = get_session_factory()
    async with async_session() as session:
        yield session


async def get_optional_db_session() -> AsyncIterator[AsyncSession | None]:
    if get_settings().database_url is None:
        yield None
        return
    async for session in get_db_session():
        yield session
