from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.repositories.resolver import PlaybackResolverRepository, ResolverLookupError
from app.db.repositories.settings import AppSettingsRepository
from app.db.session import build_session_factory
from app.resolver.manifest import ResolverManifestError, resolve_manifest_target

router = APIRouter(tags=["resolver"])


@router.api_route("/play/{entry_id}", methods=["GET", "HEAD"])
async def play(entry_id: str, token: Annotated[str, Query(min_length=1)]) -> RedirectResponse:
    settings = get_settings()
    if not await _resolver_token_is_valid(settings, token):
        raise HTTPException(status_code=403, detail="Invalid resolver token.")

    database_target = await _database_resolver_target(settings, entry_id)
    if database_target is not None:
        return RedirectResponse(database_target)

    return RedirectResponse(_manifest_resolver_target(settings, entry_id))


async def _resolver_token_is_valid(settings: Settings, token: str) -> bool:
    if settings.resolver_token is not None:
        expected_token = settings.resolver_token.get_secret_value()
        if secrets.compare_digest(token, expected_token):
            return True
    if settings.database_url is None:
        if settings.resolver_token is None:
            raise HTTPException(status_code=503, detail="Resolver is not configured.")
        return False
    try:
        session_factory = build_session_factory(settings.database_url)
        async with session_factory() as session:
            return await PlaybackResolverRepository(session).resolver_token_is_valid(token)
    except (OSError, SQLAlchemyError) as error:
        raise HTTPException(status_code=503, detail="Resolver is not available.") from error


async def _database_resolver_target(settings: Settings, entry_id: str) -> str | None:
    if settings.database_url is None:
        return None
    try:
        session_factory = build_session_factory(settings.database_url)
        async with session_factory() as session:
            api_key = await _torbox_api_key(settings, session)
            if api_key is None:
                raise HTTPException(status_code=503, detail="TorBox API key is not configured.")
            target = await PlaybackResolverRepository(session).resolve_torbox_target(
                entry_id=entry_id,
                api_key=api_key,
                torbox_base_url=settings.torbox_base_url,
            )
            return target.target_url
    except ResolverLookupError as error:
        raise HTTPException(status_code=404, detail="Resolver entry was not found.") from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except (OSError, SQLAlchemyError) as error:
        raise HTTPException(status_code=503, detail="Resolver is not available.") from error


async def _torbox_api_key(settings: Settings, session: AsyncSession) -> str | None:
    if settings.torbox_api_key is not None:
        return settings.torbox_api_key.get_secret_value()
    return await AppSettingsRepository(session, settings).provider_api_key("torbox")


def _manifest_resolver_target(settings: Settings, entry_id: str) -> str:
    if settings.library_root is None:
        raise HTTPException(status_code=503, detail="Resolver is not configured.")
    try:
        return resolve_manifest_target(settings.library_root, entry_id)
    except ResolverManifestError as error:
        raise HTTPException(status_code=404, detail="Resolver entry was not found.") from error
