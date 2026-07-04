from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.dependencies import get_db_session
from app.db.repositories.settings import AppSettingsRepository, AppSettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsResponse(BaseModel):
    base_url: str | None
    library_root: str | None
    torbox_configured: bool
    tmdb_configured: bool
    resolver_configured: bool
    base_url_source: str | None
    library_root_source: str | None
    torbox_source: str | None
    tmdb_source: str | None
    resolver_source: str | None


class SettingsUpdateRequest(BaseModel):
    base_url: str | None = Field(default=None, min_length=1)
    library_root: str | None = Field(default=None, min_length=1)
    torbox_api_key: str | None = Field(default=None, min_length=1)
    tmdb_api_key: str | None = Field(default=None, min_length=1)
    resolver_token: str | None = Field(default=None, min_length=1)


async def get_settings_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[AppSettingsRepository]:
    yield AppSettingsRepository(session, get_settings())


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
    request: SettingsUpdateRequest,
    repository: Annotated[AppSettingsRepository, Depends(get_settings_repository)],
) -> SettingsResponse:
    try:
        snapshot = await repository.save(
            AppSettingsUpdate(
                base_url=request.base_url,
                library_root=request.library_root,
                torbox_api_key=request.torbox_api_key,
                tmdb_api_key=request.tmdb_api_key,
                resolver_token=request.resolver_token,
            )
        )
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return SettingsResponse.model_validate(snapshot, from_attributes=True)


@router.delete("", response_model=SettingsResponse)
async def clear_saved_settings(
    repository: Annotated[AppSettingsRepository, Depends(get_settings_repository)],
) -> SettingsResponse:
    snapshot = await repository.clear_saved_setup()
    return SettingsResponse.model_validate(snapshot, from_attributes=True)
