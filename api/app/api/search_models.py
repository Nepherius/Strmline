from __future__ import annotations

from pydantic import BaseModel, Field

from app.search.service import StreamResult, TitleResult


class TitleSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)


class TitleSearchResponse(BaseModel):
    ok: bool
    message: str
    results: list[TitleResult] = []


class StreamSearchRequest(BaseModel):
    media_type: str = Field(pattern=r"^(movie|series)$")
    imdb_id: str | None = Field(default=None, min_length=1, max_length=20)
    tmdb_id: int | None = Field(default=None, ge=1)
    season: int | None = Field(default=None, ge=1)
    episode: int | None = Field(default=None, ge=1)


class StreamSearchResponse(BaseModel):
    ok: bool
    message: str
    stream_count: int = 0
    streams: list[StreamResult] = []


class StreamActionRequest(StreamSearchRequest):
    stream_key: str = Field(min_length=1, max_length=64)
    add_only_if_cached: bool = True
    media_title: str | None = Field(default=None, min_length=1, max_length=300)
    media_year: int | None = Field(default=None, ge=1800, le=2200)
    media_poster_path: str | None = Field(
        default=None,
        max_length=300,
        pattern=r"^/[A-Za-z0-9._-]+$",
    )


class StreamRemoveRequest(BaseModel):
    stream_key: str = Field(min_length=1, max_length=64)


class StreamActionResponse(BaseModel):
    ok: bool
    message: str
    stream_key: str
    selected: bool
    torbox_torrent_id: str | None = None
    auto_sync_status: str | None = None
    auto_sync_run_id: int | None = None
