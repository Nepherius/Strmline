from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.repositories.settings import AppSettingsRepository


async def effective_tmdb_key(
    session: AsyncSession | None,
    settings: Settings,
) -> str | None:
    if session is not None:
        try:
            repo = AppSettingsRepository(session, settings)
            return await repo.provider_api_key("tmdb")
        except RuntimeError:
            pass
    if settings.tmdb_api_key is not None:
        return settings.tmdb_api_key.get_secret_value()
    return None


async def effective_torbox_key(
    session: AsyncSession | None,
    settings: Settings,
) -> str | None:
    if session is not None:
        try:
            repo = AppSettingsRepository(session, settings)
            return await repo.provider_api_key("torbox")
        except RuntimeError:
            pass
    if settings.torbox_api_key is not None:
        return settings.torbox_api_key.get_secret_value()
    return None


async def effective_aiostreams_url(
    session: AsyncSession | None,
    settings: Settings,
) -> str | None:
    if session is not None:
        try:
            repo = AppSettingsRepository(session, settings)
            return await repo.aiostreams_base_url_value()
        except RuntimeError:
            pass
    if settings.aiostreams_base_url is not None:
        return settings.aiostreams_base_url.get_secret_value()
    return None
