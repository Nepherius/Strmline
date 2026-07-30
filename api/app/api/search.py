"""Search API routes for title discovery and stream lookup."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.file_manifests import (
    MediaFileManifestResponse,
    torbox_manifest_response,
    unavailable_manifest,
)
from app.api.provider_config import (
    effective_aiostreams_url,
    effective_tmdb_key,
    effective_torbox_key,
)
from app.api.search_models import (
    StreamActionRequest,
    StreamActionResponse,
    StreamFilesRequest,
    StreamRemoveRequest,
    StreamSearchRequest,
    StreamSearchResponse,
    TitleSearchRequest,
    TitleSearchResponse,
)
from app.core.config import Settings, get_settings
from app.db.dependencies import get_optional_db_session
from app.db.repositories.library_exclusion import LibraryExclusionRepository
from app.db.repositories.stream_selection import StreamSelectionRecord, StreamSelectionRepository
from app.db.repositories.tmdb_cache import TmdbCacheRepository
from app.providers.aiostreams.client import AioStreamsClient, AioStreamsClientError
from app.providers.tmdb.client import TmdbClient, TmdbClientError
from app.providers.tmdb.metadata import TmdbMetadataService
from app.providers.torbox.client import TorBoxAPIError, TorBoxClient
from app.providers.torbox.manifests import (
    TorBoxTorrentManifest,
    torrent_manifest_from_download,
)
from app.search.actions import (
    StreamActionError,
    StreamActionTarget,
    add_stream_to_torbox,
    remove_stream_from_torbox,
    selected_aiostreams_stream,
)
from app.search.service import (
    TitleResult,
    fetch_imdb_id_from_tmdb,
    search_streams,
    search_titles_via_tmdb,
)
from app.search.stream_identity import stream_identity
from app.search.stream_parser import is_imdb_id
from app.sync.scheduler import enqueue_post_add_sync

router = APIRouter(prefix="/api/search", tags=["search"])
logger = logging.getLogger(__name__)


class StreamFileLookupConfigurationError(RuntimeError):
    """Raised when stream file lookup is not configured."""


@router.post("/titles", response_model=TitleSearchResponse)
async def search_titles(
    request: TitleSearchRequest,
    session: Annotated[AsyncSession | None, Depends(get_optional_db_session)],
) -> TitleSearchResponse:
    """Search for titles via TMDB, or directly use an IMDB ID."""
    settings = get_settings()
    query = request.query.strip()
    logger.debug("Starting title search query_length=%d.", len(query))

    if is_imdb_id(query):
        return TitleSearchResponse(
            ok=True,
            message="IMDB ID detected. Use stream search directly.",
            results=[
                TitleResult(
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

    if session is not None:
        await session.commit()
    logger.debug("Title search completed with %d result(s).", len(results))
    return TitleSearchResponse(
        ok=True,
        message=f"Found {len(results)} result(s).",
        results=results,
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
    logger.debug(
        "Starting stream search media_type=%s season=%s episode=%s.",
        request.media_type,
        request.season,
        request.episode,
    )

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
        logger.debug("Stream search failed while requesting AIOStreams.")
        return StreamSearchResponse(
            ok=False,
            message="AIOStreams stream lookup failed.",
        )

    selected_keys = await _selected_stream_keys(session, [result.stream_key for result in results])
    if session is not None:
        await session.commit()
    logger.debug(
        "Stream search completed with %d result(s), including %d selected stream(s).",
        len(results),
        len(selected_keys),
    )
    return StreamSearchResponse(
        ok=True,
        message=f"Found {len(results)} stream(s).",
        stream_count=len(results),
        streams=[
            result.model_copy(
                update={
                    "selected": result.stream_key in selected_keys,
                    "season": request.season,
                    "episode": request.episode,
                }
            )
            for result in results
        ],
    )


@router.post("/streams/add", response_model=StreamActionResponse)
async def add_stream_endpoint(
    request: StreamActionRequest,
    http_request: Request,
    session: Annotated[AsyncSession | None, Depends(get_optional_db_session)],
) -> StreamActionResponse:
    started_at = perf_counter()
    logger.debug("Starting stream add media_type=%s.", request.media_type)
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
    action_started_at = perf_counter()
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

    queued = enqueue_post_add_sync(
        http_request.app,
        outcome.torbox_torrent_id,
    )
    auto_sync_status = "queued" if queued else "not_queued"
    message = (
        f"{outcome.message} Library update queued."
        if queued
        else f"{outcome.message} Library update will occur on the next sync."
    )
    logger.debug(
        (
            "Stream add accepted selected=%s auto_sync_status=%s "
            "action_duration_ms=%.1f total_duration_ms=%.1f."
        ),
        outcome.selected,
        auto_sync_status,
        (perf_counter() - action_started_at) * 1000,
        (perf_counter() - started_at) * 1000,
    )

    return StreamActionResponse(
        ok=True,
        message=message,
        stream_key=outcome.stream_key,
        selected=outcome.selected,
        torbox_torrent_id=outcome.torbox_torrent_id,
        auto_sync_status=auto_sync_status,
        auto_sync_run_id=None,
    )


@router.post("/streams/files", response_model=MediaFileManifestResponse)
async def stream_files_endpoint(
    request: StreamFilesRequest,
    session: Annotated[AsyncSession | None, Depends(get_optional_db_session)],
) -> MediaFileManifestResponse:
    if session is None:
        return unavailable_manifest("Database is not configured.", ok=False)
    try:
        manifest = await _load_stream_file_manifest(request, session)
    except StreamFileLookupConfigurationError as error:
        return unavailable_manifest(str(error), ok=False)
    except (AioStreamsClientError, StreamActionError, TorBoxAPIError) as error:
        return unavailable_manifest(_stream_file_error(error), ok=False)

    if manifest is None:
        return unavailable_manifest(
            "The file list is unavailable until TorBox can identify this torrent.",
        )
    return torbox_manifest_response(manifest)


def _stream_file_error(error: Exception) -> str:
    if isinstance(error, AioStreamsClientError):
        return "AIOStreams stream lookup failed."
    if isinstance(error, StreamActionError):
        return "This stream result is no longer available. Refresh the search and try again."
    logger.error("TorBox stream file lookup failed.", exc_info=error)
    return "TorBox file lookup failed."


async def _load_stream_file_manifest(
    request: StreamFilesRequest,
    session: AsyncSession,
) -> TorBoxTorrentManifest | None:
    settings = get_settings()
    media_id = await _action_media_id(request, session, settings)
    if media_id is None:
        raise StreamFileLookupConfigurationError("Could not resolve IMDB ID.")
    aiostreams_url = await effective_aiostreams_url(session, settings)
    torbox_api_key = await effective_torbox_key(session, settings)
    if aiostreams_url is None:
        raise StreamFileLookupConfigurationError("AIOStreams is not configured.")
    if torbox_api_key is None:
        raise StreamFileLookupConfigurationError("TorBox API key is not configured.")

    stream = await selected_aiostreams_stream(
        AioStreamsClient(
            base_url=aiostreams_url,
            timeout_seconds=settings.outbound_timeout_seconds,
        ),
        StreamActionTarget(
            media_type=request.media_type,
            media_id=media_id,
            stream_key=request.stream_key,
        ),
    )
    identity = stream_identity(
        stream,
        media_type=request.media_type,
        media_id=media_id,
    )
    selection = await StreamSelectionRepository(session).get(request.stream_key)
    async with TorBoxClient(
        api_key=torbox_api_key,
        base_url=settings.torbox_base_url,
        timeout=settings.outbound_timeout_seconds,
    ) as torbox_client:
        manifest = await _selected_download_manifest(torbox_client, selection, identity.info_hash)
        info_hash = identity.info_hash or (selection.info_hash if selection is not None else None)
        if manifest is None and info_hash is not None:
            return await torbox_client.cached_torrent_manifest(info_hash)
        return manifest


async def _selected_download_manifest(
    torbox_client: TorBoxClient,
    selection: StreamSelectionRecord | None,
    identity_info_hash: str | None,
) -> TorBoxTorrentManifest | None:
    if selection is None or selection.torbox_torrent_id is None:
        return None
    download = await torbox_client.get_download("torrents", selection.torbox_torrent_id)
    if download is None:
        return None
    return torrent_manifest_from_download(
        download,
        selection.info_hash or identity_info_hash,
    )


@router.post("/streams/remove", response_model=StreamActionResponse)
async def remove_stream_endpoint(
    request: StreamRemoveRequest,
    session: Annotated[AsyncSession | None, Depends(get_optional_db_session)],
) -> StreamActionResponse:
    logger.debug("Starting stream removal.")
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

    logger.debug("Stream removal completed selected=%s.", outcome.selected)
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


async def _action_media_id(
    request: StreamSearchRequest,
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
