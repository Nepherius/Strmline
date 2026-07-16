"""Search API routes for title discovery and stream lookup."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.provider_config import (
    effective_aiostreams_url,
    effective_tmdb_key,
    effective_torbox_key,
)
from app.api.search_models import (
    ParsedStreamResponse,
    StreamActionRequest,
    StreamActionResponse,
    StreamRemoveRequest,
    StreamSearchRequest,
    StreamSearchResponse,
    StreamSearchResult,
    TitleSearchRequest,
    TitleSearchResponse,
    TitleSearchResult,
)
from app.core.config import Settings, get_settings
from app.db.dependencies import get_optional_db_session
from app.db.repositories.library_exclusion import LibraryExclusionRepository
from app.db.repositories.stream_selection import StreamSelectionRepository
from app.db.repositories.tmdb_cache import TmdbCacheRepository
from app.providers.aiostreams.client import (
    AioStreamsClient,
    AioStreamsClientError,
)
from app.providers.tmdb.client import TmdbClient, TmdbClientError
from app.providers.tmdb.metadata import TmdbMetadataService
from app.providers.torbox.client import TorBoxAPIError, TorBoxClient
from app.search.actions import (
    StreamActionError,
    StreamActionTarget,
    add_stream_to_torbox,
    remove_stream_from_torbox,
)
from app.search.auto_sync import auto_sync_after_stream_add
from app.search.service import (
    StreamResult,
    TitleResult,
    fetch_imdb_id_from_tmdb,
    search_streams,
    search_titles_via_tmdb,
)
from app.search.stream_parser import is_imdb_id

router = APIRouter(prefix="/api/search", tags=["search"])
logger = logging.getLogger(__name__)


@router.post("/titles", response_model=TitleSearchResponse)
async def search_titles(
    request: TitleSearchRequest,
    session: Annotated[AsyncSession | None, Depends(get_optional_db_session)],
) -> TitleSearchResponse:
    """Search for titles via TMDB, or directly use an IMDB ID."""
    settings = get_settings()
    query = request.query.strip()

    if is_imdb_id(query):
        return TitleSearchResponse(
            ok=True,
            message="IMDB ID detected. Use stream search directly.",
            results=[
                TitleSearchResult(
                    tmdb_id=0,
                    imdb_id=query,
                    title=query,
                    year=None,
                    overview="Direct IMDB ID lookup",
                    poster_url=None,
                    poster_path=None,
                    media_type="movie",
                ),
            ],
        )

    tmdb_api_key = await effective_tmdb_key(session, settings)
    if tmdb_api_key is None:
        return TitleSearchResponse(ok=False, message="TMDB is not configured.")

    tmdb_client = TmdbClient(
        api_key=tmdb_api_key,
        base_url=settings.tmdb_base_url,
        timeout_seconds=settings.outbound_timeout_seconds,
    )

    if session is not None:
        cache_repo = TmdbCacheRepository(session)
        metadata = TmdbMetadataService(
            cache_repository=cache_repo,
            tmdb_client=tmdb_client,
        )
        get_json = metadata.get_json
    else:
        get_json = tmdb_client.get_json

    try:
        results = await search_titles_via_tmdb(
            tmdb_get_json=get_json,
            query=query,
        )
    except TmdbClientError:
        return TitleSearchResponse(ok=False, message="TMDB search failed.")

    return TitleSearchResponse(
        ok=True,
        message=f"Found {len(results)} result(s).",
        results=[_title_to_response(r) for r in results],
    )


async def _resolve_imdb_id(
    *,
    media_type: str,
    imdb_id: str | None,
    tmdb_id: int | None,
    session: AsyncSession | None,
    settings: Settings,
) -> str | None:
    if imdb_id is not None:
        return imdb_id

    if tmdb_id is None:
        return None

    tmdb_api_key = await effective_tmdb_key(session, settings)
    if tmdb_api_key is None:
        return None

    tmdb_client = TmdbClient(
        api_key=tmdb_api_key,
        base_url=settings.tmdb_base_url,
        timeout_seconds=settings.outbound_timeout_seconds,
    )

    if session is not None:
        cache_repo = TmdbCacheRepository(session)
        metadata = TmdbMetadataService(
            cache_repository=cache_repo,
            tmdb_client=tmdb_client,
        )
        get_json = metadata.get_json
    else:
        get_json = tmdb_client.get_json

    try:
        return await fetch_imdb_id_from_tmdb(
            tmdb_get_json=get_json,
            tmdb_id=tmdb_id,
            media_type=media_type,
        )
    except TmdbClientError:
        return None


@router.post("/streams", response_model=StreamSearchResponse)
async def search_streams_endpoint(
    request: StreamSearchRequest,
    session: Annotated[AsyncSession | None, Depends(get_optional_db_session)],
) -> StreamSearchResponse:
    """Query AIOStreams for sanitized stream preview results."""
    settings = get_settings()

    imdb_id = await _resolve_imdb_id(
        media_type=request.media_type,
        imdb_id=request.imdb_id,
        tmdb_id=request.tmdb_id,
        session=session,
        settings=settings,
    )
    if imdb_id is None:
        return StreamSearchResponse(
            ok=False,
            message="Could not resolve IMDB ID. Ensure credentials are set.",
        )

    aiostreams_url = await effective_aiostreams_url(session, settings)
    if aiostreams_url is None:
        return StreamSearchResponse(
            ok=False,
            message="AIOStreams is not configured. Add the URL in Setup.",
        )

    aiostreams_client = AioStreamsClient(
        base_url=aiostreams_url,
        timeout_seconds=settings.outbound_timeout_seconds,
    )

    media_id = _build_stremio_id(imdb_id, request.season, request.episode)

    try:
        results = await search_streams(
            aiostreams_client=aiostreams_client,
            media_type=request.media_type,
            media_id=media_id,
        )
    except AioStreamsClientError:
        return StreamSearchResponse(
            ok=False,
            message="AIOStreams stream lookup failed.",
        )

    selected_keys = await _selected_stream_keys(session, [result.stream_key for result in results])
    return StreamSearchResponse(
        ok=True,
        message=f"Found {len(results)} stream(s).",
        stream_count=len(results),
        streams=[
            _stream_to_response(
                result,
                selected=result.stream_key in selected_keys,
                season=request.season,
                episode=request.episode,
            )
            for result in results
        ],
    )


@router.post("/streams/add", response_model=StreamActionResponse)
async def add_stream_endpoint(
    request: StreamActionRequest,
    session: Annotated[AsyncSession | None, Depends(get_optional_db_session)],
) -> StreamActionResponse:
    if session is None:
        return _action_response(
            request.stream_key,
            selected=False,
            message="Database is not configured.",
        )

    settings = get_settings()
    media_id = await _action_media_id(request, session, settings)
    if media_id is None:
        return _action_response(
            request.stream_key,
            selected=False,
            message="Could not resolve IMDB ID.",
        )

    aiostreams_url = await effective_aiostreams_url(session, settings)
    torbox_api_key = await effective_torbox_key(session, settings)
    if aiostreams_url is None:
        return _action_response(
            request.stream_key,
            selected=False,
            message="AIOStreams is not configured.",
        )
    if torbox_api_key is None:
        return _action_response(
            request.stream_key,
            selected=False,
            message="TorBox API key is not configured.",
        )

    aiostreams_client = AioStreamsClient(
        base_url=aiostreams_url,
        timeout_seconds=settings.outbound_timeout_seconds,
    )
    try:
        async with TorBoxClient(
            api_key=torbox_api_key,
            base_url=settings.torbox_base_url,
            timeout=settings.outbound_timeout_seconds,
        ) as torbox_client:
            outcome = await add_stream_to_torbox(
                aiostreams_client=aiostreams_client,
                torbox_client=torbox_client,
                repository=StreamSelectionRepository(session),
                target=StreamActionTarget(
                    media_type=request.media_type,
                    media_id=media_id,
                    stream_key=request.stream_key,
                    tmdb_id=str(request.tmdb_id) if request.tmdb_id is not None else None,
                    media_title=request.media_title,
                    media_year=request.media_year,
                    media_poster_path=request.media_poster_path,
                ),
                add_only_if_cached=request.add_only_if_cached,
            )
        if request.media_title is not None:
            _ = await LibraryExclusionRepository(session).clear_for_selected_media(
                media_type=request.media_type,
                title=request.media_title,
                year=request.media_year,
            )
        await session.commit()
    except (AioStreamsClientError, StreamActionError, TorBoxAPIError) as error:
        await session.rollback()
        return _action_response(
            request.stream_key,
            selected=False,
            message=_safe_action_message(error),
        )

    auto_sync = await auto_sync_after_stream_add(
        session=session,
        settings=settings,
        action_message=outcome.message,
    )

    return StreamActionResponse(
        ok=True,
        message=auto_sync.message,
        stream_key=outcome.stream_key,
        selected=outcome.selected,
        torbox_torrent_id=outcome.torbox_torrent_id,
        auto_sync_status=auto_sync.status,
        auto_sync_run_id=auto_sync.sync_run_id,
    )


@router.post("/streams/remove", response_model=StreamActionResponse)
async def remove_stream_endpoint(
    request: StreamRemoveRequest,
    session: Annotated[AsyncSession | None, Depends(get_optional_db_session)],
) -> StreamActionResponse:
    if session is None:
        return _action_response(
            request.stream_key,
            selected=False,
            message="Database is not configured.",
        )

    settings = get_settings()
    torbox_api_key = await effective_torbox_key(session, settings)
    if torbox_api_key is None:
        return _action_response(
            request.stream_key,
            selected=False,
            message="TorBox API key is not configured.",
        )

    try:
        async with TorBoxClient(
            api_key=torbox_api_key,
            base_url=settings.torbox_base_url,
            timeout=settings.outbound_timeout_seconds,
        ) as torbox_client:
            outcome = await remove_stream_from_torbox(
                torbox_client=torbox_client,
                repository=StreamSelectionRepository(session),
                stream_key=request.stream_key,
            )
        await session.commit()
    except TorBoxAPIError as error:
        await session.rollback()
        return _action_response(
            request.stream_key,
            selected=True,
            message=_safe_action_message(error),
        )

    return StreamActionResponse(
        ok=True,
        message=outcome.message,
        stream_key=outcome.stream_key,
        selected=outcome.selected,
        torbox_torrent_id=outcome.torbox_torrent_id,
    )


def _build_stremio_id(imdb_id: str, season: int | None, episode: int | None) -> str:
    """Build a Stremio-compatible media ID."""
    if season is not None and episode is not None:
        return f"{imdb_id}:{season}:{episode}"
    return imdb_id


def _title_to_response(result: TitleResult) -> TitleSearchResult:
    poster_url: str | None = None
    if result.poster_path:
        poster_url = f"https://image.tmdb.org/t/p/w342{result.poster_path}"
    return TitleSearchResult(
        tmdb_id=result.tmdb_id,
        imdb_id=result.imdb_id,
        title=result.title,
        year=result.year,
        overview=result.overview,
        poster_url=poster_url,
        poster_path=result.poster_path,
        media_type=result.media_type,
    )


async def _action_media_id(
    request: StreamActionRequest,
    session: AsyncSession,
    settings: Settings,
) -> str | None:
    imdb_id = await _resolve_imdb_id(
        media_type=request.media_type,
        imdb_id=request.imdb_id,
        tmdb_id=request.tmdb_id,
        session=session,
        settings=settings,
    )
    if imdb_id is None:
        return None
    return _build_stremio_id(imdb_id, request.season, request.episode)


def _stream_to_response(
    result: StreamResult,
    *,
    selected: bool,
    season: int | None,
    episode: int | None,
) -> StreamSearchResult:
    return StreamSearchResult(
        stream_key=result.stream_key,
        title=result.title,
        season=season,
        episode=episode,
        parsed=ParsedStreamResponse(
            quality=result.parsed.quality,
            codec=result.parsed.codec,
            hdr=result.parsed.hdr,
            audio=result.parsed.audio,
            size_bytes=result.parsed.size_bytes,
            size_label=result.parsed.size_label,
            source=result.parsed.source,
            language=result.parsed.language,
        ),
        cached=result.cached,
        has_url=result.has_url,
        has_info_hash=result.has_info_hash,
        addable=result.addable,
        selected=selected,
        provider_label=result.provider_label,
        seeders=result.seeders,
    )


def _action_response(
    stream_key: str,
    *,
    selected: bool,
    message: str,
) -> StreamActionResponse:
    return StreamActionResponse(
        ok=False,
        message=message,
        stream_key=stream_key,
        selected=selected,
        torbox_torrent_id=None,
    )


def _safe_action_message(error: Exception) -> str:
    if isinstance(error, StreamActionError):
        return str(error)
    if isinstance(error, AioStreamsClientError):
        return "AIOStreams stream lookup failed."
    if isinstance(error, TorBoxAPIError):
        logger.error("TorBox stream action failed.")
        return "TorBox operation failed."
    return "Stream action failed."


async def _selected_stream_keys(
    session: AsyncSession | None,
    stream_keys: list[str],
) -> set[str]:
    if session is None:
        return set()
    return await StreamSelectionRepository(session).selected_keys(stream_keys)
