from __future__ import annotations

from pydantic import BaseModel, Field


class TitleSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)


class TitleSearchResult(BaseModel):
    tmdb_id: int
    imdb_id: str | None
    title: str
    year: str | None
    overview: str
    poster_url: str | None
    poster_path: str | None
    media_type: str


class TitleSearchResponse(BaseModel):
    ok: bool
    message: str
    results: list[TitleSearchResult] = []


class StreamSearchRequest(BaseModel):
    media_type: str = Field(pattern=r"^(movie|series)$")
    imdb_id: str | None = Field(default=None, min_length=1, max_length=20)
    tmdb_id: int | None = Field(default=None, ge=1)
    season: int | None = Field(default=None, ge=1)
    episode: int | None = Field(default=None, ge=1)


class ParsedStreamResponse(BaseModel):
    quality: str | None
    codec: str | None
    hdr: str | None
    audio: str | None
    size_bytes: int | None
    size_label: str | None
    source: str | None
    language: str | None


class StreamSearchResult(BaseModel):
    stream_key: str
    title: str
    season: int | None
    episode: int | None
    parsed: ParsedStreamResponse
    cached: bool | None
    has_url: bool
    has_info_hash: bool
    addable: bool
    selected: bool
    provider_label: str | None
    seeders: int | None


class StreamSearchResponse(BaseModel):
    ok: bool
    message: str
    stream_count: int = 0
    streams: list[StreamSearchResult] = []


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
