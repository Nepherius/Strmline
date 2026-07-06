"""Search orchestration: TMDB title lookup and AIOStreams stream preview."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from app.providers.aiostreams.client import AioStreamsClient, AioStreamsStream
from app.search.stream_identity import stream_identity
from app.search.stream_parser import ParsedStream, parse_stream

MIN_YEAR_LENGTH = 4


@dataclass(frozen=True, slots=True)
class TitleResult:
    """A single TMDB title search result."""

    tmdb_id: int
    imdb_id: str | None
    title: str
    year: str | None
    overview: str
    poster_path: str | None
    media_type: str


@dataclass(frozen=True, slots=True)
class StreamResult:
    """A single stream result with parsed metadata and cache status."""

    stream_key: str
    title: str
    parsed: ParsedStream
    cached: bool | None
    has_url: bool
    has_info_hash: bool
    addable: bool
    provider_label: str | None
    seeders: int | None


class SearchServiceError(RuntimeError):
    """Raised when search orchestration fails safely."""


async def search_titles_via_tmdb(
    *,
    tmdb_get_json: TmdbGetJson,
    query: str,
) -> list[TitleResult]:
    """Search TMDB for titles matching a query string."""
    payload = await tmdb_get_json(
        "/search/multi",
        params={"query": query, "include_adult": "false"},
    )
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        return []
    results: list[TitleResult] = []
    for raw in cast(list[object], raw_results)[:20]:
        if not isinstance(raw, dict):
            continue
        result = _title_from_tmdb(cast(dict[str, Any], raw))
        if result is not None:
            results.append(result)
    return results


async def fetch_imdb_id_from_tmdb(
    *,
    tmdb_get_json: TmdbGetJson,
    tmdb_id: int,
    media_type: str,
) -> str | None:
    """Look up the IMDB ID for a TMDB entry via the external IDs endpoint."""
    if media_type == "movie":
        endpoint = f"/movie/{tmdb_id}/external_ids"
    else:
        endpoint = f"/tv/{tmdb_id}/external_ids"
    payload = await tmdb_get_json(endpoint)
    imdb_id = payload.get("imdb_id")
    return imdb_id if isinstance(imdb_id, str) and imdb_id.startswith("tt") else None


async def search_streams(
    *,
    aiostreams_client: AioStreamsClient,
    media_type: str,
    media_id: str,
) -> list[StreamResult]:
    """Query AIOStreams for sanitized stream preview results."""
    stremio_type = "movie" if media_type == "movie" else "series"
    streams = await aiostreams_client.streams(
        media_type=stremio_type,
        media_id=media_id,
    )
    return [
        _build_stream_result(stream, media_type=media_type, media_id=media_id) for stream in streams
    ]


TmdbGetJson = Any  # Callable protocol - see metadata.py TmdbJsonClient


def _title_from_tmdb(
    raw: dict[str, Any],
) -> TitleResult | None:
    tmdb_id = raw.get("id")
    if not isinstance(tmdb_id, int):
        return None

    media_type = _normalized_media_type(raw.get("media_type"))
    if media_type is None:
        return None

    if media_type == "movie":
        title = _str_or_none(raw.get("title")) or _str_or_none(raw.get("original_title"))
        release_date = _str_or_none(raw.get("release_date"))
    else:
        title = _str_or_none(raw.get("name")) or _str_or_none(raw.get("original_name"))
        release_date = _str_or_none(raw.get("first_air_date"))

    if not title:
        return None

    year = (
        release_date[:MIN_YEAR_LENGTH]
        if release_date and len(release_date) >= MIN_YEAR_LENGTH
        else None
    )
    overview = _str_or_none(raw.get("overview")) or ""
    poster_path = _str_or_none(raw.get("poster_path"))

    return TitleResult(
        tmdb_id=tmdb_id,
        imdb_id=None,
        title=title,
        year=year,
        overview=overview,
        poster_path=poster_path,
        media_type=media_type,
    )


def _build_stream_result(
    stream: AioStreamsStream,
    *,
    media_type: str,
    media_id: str,
) -> StreamResult:
    filename = stream.behavior_hints.get("filename")
    safe_filename = filename if isinstance(filename, str) else None
    video_size = stream.behavior_hints.get("videoSize")
    safe_video_size = video_size if isinstance(video_size, int) else None
    seeders_hint = stream.behavior_hints.get("seeders")
    safe_seeders = seeders_hint if isinstance(seeders_hint, int) else None

    parsed = parse_stream(
        title=stream.title,
        description=stream.description,
        name=stream.name,
        filename=safe_filename,
        video_size=safe_video_size,
    )

    label = _stream_label(stream_name=stream.name, filename=safe_filename, title=stream.title)
    identity = stream_identity(stream, media_type=media_type, media_id=media_id)

    return StreamResult(
        stream_key=identity.stream_key,
        title=label,
        parsed=parsed,
        cached=None,
        has_url=stream.url is not None,
        has_info_hash=stream.info_hash is not None,
        addable=identity.addable,
        provider_label=_provider_label_from_stream(stream),
        seeders=safe_seeders,
    )


def _stream_label(*, stream_name: str | None, filename: str | None, title: str | None) -> str:
    base = filename or title or stream_name or "Unknown"
    if stream_name is None:
        return base
    if base == stream_name or base.startswith(f"{stream_name} "):
        return base
    return f"{stream_name} - {base}"


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _provider_label_from_stream(stream: AioStreamsStream) -> str | None:
    combined = " ".join(
        field
        for field in (stream.name, stream.title, stream.description)
        if field is not None and field.strip()
    )
    normalized = combined.lower()
    if "instant tb" in normalized:
        return "Instant TB"
    if "cast (tb" in normalized:
        return "Cast TB"
    if "dl with tb" in normalized:
        return "DL with TB"
    return None


def _normalized_media_type(value: object) -> str | None:
    if value == "movie":
        return "movie"
    if value == "tv":
        return "series"
    return None
