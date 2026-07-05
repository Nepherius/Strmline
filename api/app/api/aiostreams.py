from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.dependencies import get_optional_db_session
from app.db.repositories.settings import AppSettingsRepository
from app.providers.aiostreams.client import (
    AioStreamsClient,
    AioStreamsClientError,
    AioStreamsManifest,
    AioStreamsStream,
)

router = APIRouter(prefix="/api/providers/aiostreams", tags=["providers"])


class AioStreamsTestRequest(BaseModel):
    base_url: str | None = Field(default=None, min_length=1)
    media_type: str | None = Field(default=None, min_length=1)
    media_id: str | None = Field(default=None, min_length=1)


class AioStreamsStreamResponse(BaseModel):
    name: str | None
    title: str | None
    description: str | None
    has_url: bool
    has_info_hash: bool
    file_idx: int | None
    behavior_hints: dict[str, Any]


def _empty_stream_responses() -> list[AioStreamsStreamResponse]:
    return []


class AioStreamsTestResponse(BaseModel):
    ok: bool
    message: str
    addon_name: str | None = None
    addon_version: str | None = None
    resources: list[str] = Field(default_factory=list)
    types: list[str] = Field(default_factory=list)
    stream_count: int | None = None
    streams: list[AioStreamsStreamResponse] = Field(default_factory=_empty_stream_responses)


@router.post("/test", response_model=AioStreamsTestResponse)
async def test_aiostreams(
    request: AioStreamsTestRequest,
    session: Annotated[AsyncSession | None, Depends(get_optional_db_session)],
) -> AioStreamsTestResponse:
    settings = get_settings()
    base_url = await _effective_base_url(request.base_url, session)
    if base_url is None:
        return AioStreamsTestResponse(
            ok=False,
            message="AIOStreams URL is not configured.",
        )
    client = AioStreamsClient(
        base_url=base_url,
        timeout_seconds=settings.outbound_timeout_seconds,
    )
    try:
        manifest = await client.manifest()
        streams: tuple[AioStreamsStream, ...] = ()
        if request.media_type is not None and request.media_id is not None:
            streams = await client.streams(media_type=request.media_type, media_id=request.media_id)
    except AioStreamsClientError:
        return AioStreamsTestResponse(ok=False, message="AIOStreams connection failed.")
    return _test_response(manifest, streams)


async def _effective_base_url(
    request_base_url: str | None,
    session: AsyncSession | None,
) -> str | None:
    if request_base_url is not None:
        return request_base_url
    settings = get_settings()
    if session is not None:
        try:
            return await AppSettingsRepository(session, settings).aiostreams_base_url_value()
        except RuntimeError:
            return None
    if settings.aiostreams_base_url is not None:
        return settings.aiostreams_base_url.get_secret_value()
    return None


def _test_response(
    manifest: AioStreamsManifest,
    streams: tuple[AioStreamsStream, ...],
) -> AioStreamsTestResponse:
    return AioStreamsTestResponse(
        ok=True,
        message="AIOStreams connection succeeded.",
        addon_name=manifest.name,
        addon_version=manifest.version,
        resources=list(manifest.resources),
        types=list(manifest.types),
        stream_count=len(streams) if streams else None,
        streams=[_stream_response(stream) for stream in streams[:5]],
    )


def _stream_response(stream: AioStreamsStream) -> AioStreamsStreamResponse:
    return AioStreamsStreamResponse(
        name=stream.name,
        title=stream.title,
        description=stream.description,
        has_url=stream.url is not None,
        has_info_hash=stream.info_hash is not None,
        file_idx=stream.file_idx,
        behavior_hints=_safe_behavior_hints(stream.behavior_hints),
    )


def _safe_behavior_hints(behavior_hints: dict[str, Any]) -> dict[str, Any]:
    safe_hints: dict[str, Any] = {}
    filename = behavior_hints.get("filename")
    video_size = behavior_hints.get("videoSize")
    binge_group = behavior_hints.get("bingeGroup")
    if isinstance(filename, str) and filename.strip():
        safe_hints["filename"] = filename
    if isinstance(video_size, int) and not isinstance(video_size, bool):
        safe_hints["videoSize"] = video_size
    if isinstance(binge_group, str) and binge_group.strip():
        safe_hints["bingeGroup"] = binge_group
    return safe_hints
