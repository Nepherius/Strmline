from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.dependencies import get_optional_db_session
from app.db.models import User
from app.db.repositories.settings import AppSettingsRepository, ProviderName, SettingsSnapshot
from app.providers.tmdb.connection import TmdbConnectionError, check_tmdb_connection
from app.providers.torbox.connection import TorBoxConnectionError, check_torbox_connection

router = APIRouter(prefix="/api/setup", tags=["setup"])
logger = logging.getLogger(__name__)

SETUP_FIELDS = ("torbox_api_key",)


class SetupStatusResponse(BaseModel):
    configured: bool
    missing: list[str]


class ConnectionTestResponse(BaseModel):
    ok: bool
    message: str


class TorBoxConnectionTestRequest(BaseModel):
    torbox_api_key: str | None = Field(default=None, min_length=1)


class TmdbConnectionTestRequest(BaseModel):
    tmdb_api_key: str | None = Field(default=None, min_length=1)


@router.get("/status", response_model=SetupStatusResponse)
async def setup_status(
    session: Annotated[AsyncSession | None, Depends(get_optional_db_session)],
) -> SetupStatusResponse:
    missing = await setup_missing_fields(session)
    return SetupStatusResponse(
        configured=not missing,
        missing=missing,
    )


@router.post("/test/torbox", response_model=ConnectionTestResponse)
async def test_torbox(
    request: TorBoxConnectionTestRequest,
    session: Annotated[AsyncSession | None, Depends(get_optional_db_session)],
) -> ConnectionTestResponse:
    logger.debug("Starting TorBox connection test.")
    settings = get_settings()
    api_key = request.torbox_api_key or await _effective_provider_api_key("torbox", session)
    if api_key is None:
        return ConnectionTestResponse(
            ok=False,
            message="TorBox API key is not configured.",
        )
    try:
        await check_torbox_connection(
            api_key=api_key,
            base_url=settings.torbox_base_url,
            timeout_seconds=settings.outbound_timeout_seconds,
        )
    except TorBoxConnectionError:
        logger.debug("TorBox connection test failed.")
        return ConnectionTestResponse(ok=False, message="TorBox connection failed.")
    logger.debug("TorBox connection test succeeded.")
    return ConnectionTestResponse(ok=True, message="TorBox connection succeeded.")


@router.post("/test/tmdb", response_model=ConnectionTestResponse)
async def test_tmdb(
    request: TmdbConnectionTestRequest,
    session: Annotated[AsyncSession | None, Depends(get_optional_db_session)],
) -> ConnectionTestResponse:
    logger.debug("Starting TMDB connection test.")
    settings = get_settings()
    api_key = request.tmdb_api_key or await _effective_provider_api_key("tmdb", session)
    if api_key is None:
        return ConnectionTestResponse(
            ok=False,
            message="TMDB API key is not configured.",
        )
    try:
        await check_tmdb_connection(
            api_key=api_key,
            base_url=settings.tmdb_base_url,
            timeout_seconds=settings.outbound_timeout_seconds,
        )
    except TmdbConnectionError:
        logger.debug("TMDB connection test failed.")
        return ConnectionTestResponse(ok=False, message="TMDB connection failed.")
    logger.debug("TMDB connection test succeeded.")
    return ConnectionTestResponse(ok=True, message="TMDB connection succeeded.")


async def setup_missing_fields(session: AsyncSession | None) -> list[str]:
    settings = get_settings()
    snapshot = await _settings_snapshot(session)

    has_user = False
    if session is not None and hasattr(session, "execute"):
        try:
            user_count_result = await session.execute(select(User).limit(1))
            has_user = user_count_result.scalar_one_or_none() is not None
        except SQLAlchemyError:
            # DB table might not exist yet during initial run before migration
            has_user = False

    configured = {
        "torbox_api_key": settings.torbox_api_key is not None
        or (snapshot is not None and snapshot.torbox_configured),
    }
    missing = [field for field in SETUP_FIELDS if not configured[field]]
    if not has_user:
        missing.append("admin_user")
    return missing


async def _effective_provider_api_key(
    provider: ProviderName,
    session: AsyncSession | None,
) -> str | None:
    settings = get_settings()
    if provider == "torbox" and settings.torbox_api_key is not None:
        return settings.torbox_api_key.get_secret_value()
    if provider == "tmdb" and settings.tmdb_api_key is not None:
        return settings.tmdb_api_key.get_secret_value()
    if session is None:
        return None
    try:
        return await AppSettingsRepository(session, settings).provider_api_key(provider)
    except (RuntimeError, OSError, SQLAlchemyError):
        return None


async def _settings_snapshot(session: AsyncSession | None) -> SettingsSnapshot | None:
    settings = get_settings()
    if session is None:
        return None
    try:
        return await AppSettingsRepository(session, settings).snapshot_with_env()
    except (OSError, SQLAlchemyError):
        return None
