from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import configure_debug_logging
from app.db.dependencies import get_db_session
from app.db.repositories.settings import AppSettingsRepository, AppSettingsUpdate, PlaybackMode
from app.sync.scheduler import reschedule_auto_sync_scheduler

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsResponse(BaseModel):
    base_url: str | None
    library_root: str | None
    movies_enabled: bool
    shows_enabled: bool
    anime_enabled: bool
    playback_mode: PlaybackMode
    sync_interval_minutes: int
    debug_logging: bool = False
    season_auto_complete_enabled: bool = False
    season_auto_complete_interval_days: int = 1
    season_auto_complete_allow_uncached: bool = False
    season_auto_complete_shows_per_minute: int = 1
    torbox_configured: bool
    tmdb_configured: bool
    resolver_configured: bool
    aiostreams_configured: bool
    base_url_source: str | None
    library_root_source: str | None
    torbox_source: str | None
    tmdb_source: str | None
    resolver_source: str | None
    aiostreams_source: str | None


async def get_settings_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[AppSettingsRepository]:
    try:
        yield AppSettingsRepository(session, get_settings())
    except Exception:
        await session.rollback()
        raise
    else:
        await session.commit()


@router.get("", response_model=SettingsResponse)
async def read_settings(
    repository: Annotated[AppSettingsRepository, Depends(get_settings_repository)],
) -> SettingsResponse:
    return SettingsResponse.model_validate(
        await repository.snapshot_with_env(),
        from_attributes=True,
    )


@router.put("", response_model=SettingsResponse)
async def update_settings(
    request: AppSettingsUpdate,
    http_request: Request,
    repository: Annotated[AppSettingsRepository, Depends(get_settings_repository)],
) -> SettingsResponse:
    try:
        snapshot = await repository.save(request)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    configure_debug_logging(enabled=snapshot.debug_logging)
    await reschedule_auto_sync_scheduler(http_request.app)
    return SettingsResponse.model_validate(snapshot, from_attributes=True)


@router.delete("", response_model=SettingsResponse)
async def clear_saved_settings(
    http_request: Request,
    repository: Annotated[AppSettingsRepository, Depends(get_settings_repository)],
) -> SettingsResponse:
    snapshot = await repository.clear_saved_setup()
    configure_debug_logging(enabled=snapshot.debug_logging)
    await reschedule_auto_sync_scheduler(http_request.app)
    return SettingsResponse.model_validate(snapshot, from_attributes=True)
