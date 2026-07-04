from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.repositories.settings import AppSettingsRepository, SettingsSnapshot
from app.db.session import build_session_factory

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


@router.get("/status", response_model=SetupStatusResponse)
async def setup_status() -> SetupStatusResponse:
    missing = await setup_missing_fields()
    return SetupStatusResponse(
        configured=not missing,
        missing=missing,
    )


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
