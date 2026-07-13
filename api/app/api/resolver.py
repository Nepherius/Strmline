from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.dependencies import get_optional_db_session
from app.db.repositories.resolver import PlaybackResolverRepository, ResolverLookupError
from app.db.repositories.settings import AppSettingsRepository
from app.resolver.manifest import ResolverManifestError, resolve_manifest_target

router = APIRouter(tags=["resolver"])


@router.get("/play/{entry_id}", operation_id="play")
async def play(
    entry_id: str,
    token: Annotated[str, Query(min_length=1)],
    session: Annotated[AsyncSession | None, Depends(get_optional_db_session)],
) -> RedirectResponse:
    return await _play(entry_id, token, session)


@router.head("/play/{entry_id}", operation_id="play_head")
async def play_head(
    entry_id: str,
    token: Annotated[str, Query(min_length=1)],
    session: Annotated[AsyncSession | None, Depends(get_optional_db_session)],
) -> RedirectResponse:
    return await _play(entry_id, token, session)


async def _play(
    entry_id: str,
    token: str,
    session: AsyncSession | None,
) -> RedirectResponse:
    settings = get_settings()
    if not await _resolver_token_is_valid(settings, token, session):
        raise HTTPException(status_code=403, detail="Invalid resolver token.")

    database_target = await _database_resolver_target(settings, entry_id, session)
    if database_target is not None:
        return RedirectResponse(database_target)

    return RedirectResponse(_manifest_resolver_target(settings, entry_id))


async def _resolver_token_is_valid(
    settings: Settings,
    token: str,
    session: AsyncSession | None,
) -> bool:
    if settings.resolver_token is not None:
        expected_token = settings.resolver_token.get_secret_value()
        if secrets.compare_digest(token, expected_token):
            return True
    if session is None:
        if settings.resolver_token is None:
            raise HTTPException(status_code=503, detail="Resolver is not configured.")
        return False
    try:
        return await PlaybackResolverRepository(session).resolver_token_is_valid(token)
    except (OSError, SQLAlchemyError) as error:
        raise HTTPException(status_code=503, detail="Resolver is not available.") from error


async def _database_resolver_target(
    settings: Settings,
    entry_id: str,
    session: AsyncSession | None,
) -> str | None:
    if session is None:
        return None
    try:
        api_key = await _torbox_api_key(settings, session)
        if api_key is None:
            raise HTTPException(status_code=503, detail="TorBox API key is not configured.")
        target = await PlaybackResolverRepository(session).resolve_torbox_target(
            entry_id=entry_id,
            api_key=api_key,
            torbox_base_url=settings.torbox_base_url,
        )
    except ResolverLookupError as error:
        raise HTTPException(status_code=404, detail="Resolver entry was not found.") from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except (OSError, SQLAlchemyError) as error:
        raise HTTPException(status_code=503, detail="Resolver is not available.") from error
    else:
        return target.target_url


async def _torbox_api_key(settings: Settings, session: AsyncSession) -> str | None:
    if settings.torbox_api_key is not None:
        return settings.torbox_api_key.get_secret_value()
    return await AppSettingsRepository(session, settings).provider_api_key("torbox")


def _manifest_resolver_target(settings: Settings, entry_id: str) -> str:
    try:
        return resolve_manifest_target(settings.library_root, entry_id)
    except ResolverManifestError as error:
        raise HTTPException(status_code=404, detail="Resolver entry was not found.") from error
