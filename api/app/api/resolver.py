from __future__ import annotations

import secrets
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.dependencies import get_optional_db_session
from app.db.repositories.resolver import (
    PlaybackResolverRepository,
    ResolverLookupError,
    ResolverRecoveryError,
)
from app.db.repositories.settings import AppSettingsRepository
from app.operations.metrics import get_operational_metrics
from app.providers.torbox.client import TorBoxAPIError, TorBoxClient
from app.resolver.failure_guard import (
    ResolverFailureGuard,
    ResolverFailureGuardConfig,
    ResolverTemporarilyUnavailableError,
)
from app.resolver.manifest import ResolverManifestError, resolve_manifest_target
from app.resolver.target_cache import ResolvedTargetCache

router = APIRouter(tags=["resolver"])

RESOLVED_TARGET_CACHE_TTL_SECONDS = 30.0
RESOLVED_TARGET_CACHE_MAX_ENTRIES = 1_024

_resolved_target_cache = ResolvedTargetCache(
    ttl_seconds=RESOLVED_TARGET_CACHE_TTL_SECONDS,
    max_entries=RESOLVED_TARGET_CACHE_MAX_ENTRIES,
)
_failure_guard = ResolverFailureGuard(ResolverFailureGuardConfig())


def clear_resolved_target_cache() -> None:
    _resolved_target_cache.clear()
    _failure_guard.clear()


def configure_resolver_failure_guard(
    *,
    negative_cache_seconds: int,
    circuit_failures: int,
    circuit_window_seconds: int,
    circuit_cooldown_seconds: int,
) -> None:
    _failure_guard.reconfigure(
        ResolverFailureGuardConfig(
            negative_cache_seconds=negative_cache_seconds,
            circuit_failures=circuit_failures,
            circuit_window_seconds=circuit_window_seconds,
            circuit_cooldown_seconds=circuit_cooldown_seconds,
        )
    )


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

    database_target = await _cached_database_resolver_target(settings, entry_id, session)
    if database_target is not None:
        return _redirect(database_target)

    return _redirect(_manifest_resolver_target(settings, entry_id))


async def _cached_database_resolver_target(
    settings: Settings,
    entry_id: str,
    session: AsyncSession | None,
) -> str | None:
    if session is None:
        return None
    cached_target = _resolved_target_cache.get(entry_id)
    if cached_target is not None:
        get_operational_metrics().resolver_cache_hit()
        return cached_target
    get_operational_metrics().resolver_cache_miss()
    target = await _database_resolver_target(settings, entry_id, session)
    if target is not None:
        _resolved_target_cache.put(entry_id, target)
    return target


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
    guard = _failure_guard
    _check_resolver_guard(guard, entry_id)
    try:
        target_url = await _request_database_target(settings, entry_id, session)
    except ResolverLookupError as error:
        await session.commit()
        raise HTTPException(status_code=404, detail="Resolver entry was not found.") from error
    except (ResolverRecoveryError, TorBoxAPIError) as error:
        guard.record_failure(entry_id)
        raise HTTPException(status_code=503, detail=str(error)) from error
    except (OSError, httpx.HTTPError) as error:
        guard.record_failure(entry_id)
        raise HTTPException(status_code=503, detail="Resolver is not available.") from error
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="Resolver is not available.") from error
    else:
        guard.record_success(entry_id)
        await session.commit()
        return target_url


def _check_resolver_guard(guard: ResolverFailureGuard, entry_id: str) -> None:
    try:
        guard.check(entry_id)
    except ResolverTemporarilyUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


async def _request_database_target(
    settings: Settings,
    entry_id: str,
    session: AsyncSession,
) -> str:
    api_key = await _torbox_api_key(settings, session)
    if api_key is None:
        raise HTTPException(status_code=503, detail="TorBox API key is not configured.")
    async with TorBoxClient(
        api_key=api_key,
        base_url=settings.torbox_base_url,
        timeout=settings.outbound_timeout_seconds,
    ) as torbox_client:
        target = await PlaybackResolverRepository(session).resolve_torbox_target(
            entry_id=entry_id,
            api_key=api_key,
            torbox_base_url=settings.torbox_base_url,
            torbox_client=torbox_client,
        )
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


def _redirect(target_url: str) -> RedirectResponse:
    return RedirectResponse(target_url, headers={"Cache-Control": "no-store"})
