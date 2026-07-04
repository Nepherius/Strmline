from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.repositories.settings import AppSettingsRepository, SettingsSnapshot
from app.db.session import build_session_factory
from app.providers.torbox.connection import TorBoxConnectionError, check_torbox_connection

router = APIRouter(prefix="/api/setup", tags=["setup"])

SETUP_FIELDS = (
    "base_url",
    "database_url",
    "library_root",
    "resolver_token",
    "tmdb_api_key",
    "torbox_api_key",
)


class SetupStatusResponse(BaseModel):
    configured: bool
    missing: list[str]


class ConnectionTestResponse(BaseModel):
    ok: bool
    message: str


class TorBoxConnectionTestRequest(BaseModel):
    torbox_api_key: str | None = Field(default=None, min_length=1)


@router.get("/status", response_model=SetupStatusResponse)
async def setup_status() -> SetupStatusResponse:
    missing = await setup_missing_fields()
    return SetupStatusResponse(
        configured=not missing,
        missing=missing,
    )


@router.post("/test/torbox", response_model=ConnectionTestResponse)
async def test_torbox(request: TorBoxConnectionTestRequest) -> ConnectionTestResponse:
    settings = get_settings()
    api_key = request.torbox_api_key or await _effective_torbox_api_key()
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
        return ConnectionTestResponse(ok=False, message="TorBox connection failed.")
    return ConnectionTestResponse(ok=True, message="TorBox connection succeeded.")


async def setup_missing_fields() -> list[str]:
    settings = get_settings()
    snapshot = await _settings_snapshot()
    configured = {
        "base_url": settings.base_url is not None
        or (snapshot is not None and snapshot.base_url is not None),
        "database_url": settings.database_url is not None,
        "library_root": settings.library_root is not None
        or (snapshot is not None and snapshot.library_root is not None),
        "resolver_token": settings.resolver_token is not None
        or (snapshot is not None and snapshot.resolver_configured),
        "tmdb_api_key": settings.tmdb_api_key is not None
        or (snapshot is not None and snapshot.tmdb_configured),
        "torbox_api_key": settings.torbox_api_key is not None
        or (snapshot is not None and snapshot.torbox_configured),
    }
    return [field for field in SETUP_FIELDS if not configured[field]]


async def _effective_torbox_api_key() -> str | None:
    settings = get_settings()
    if settings.torbox_api_key is not None:
        return settings.torbox_api_key.get_secret_value()
    if settings.database_url is None:
        return None
    try:
        session_factory = build_session_factory(settings.database_url)
        async with session_factory() as session:
            return await AppSettingsRepository(session, settings).provider_api_key("torbox")
    except (RuntimeError, OSError, SQLAlchemyError):
        return None


async def _settings_snapshot() -> SettingsSnapshot | None:
    settings = get_settings()
    if settings.database_url is None:
        return None
    try:
        session_factory = build_session_factory(settings.database_url)
        async with session_factory() as session:
            return await AppSettingsRepository(session, settings).snapshot_with_env()
    except (OSError, SQLAlchemyError):
        return None
