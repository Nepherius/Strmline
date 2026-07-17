from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from app.domain.normalization import normalize_info_hash
from app.providers.aiostreams.client import AioStreamsStream

STREAM_KEY_LENGTH = 32


@dataclass(frozen=True, slots=True)
class StreamIdentity:
    stream_key: str
    info_hash: str | None
    magnet: str | None
    action_url: str | None

    @property
    def addable(self) -> bool:
        return (
            self.info_hash is not None and self.magnet is not None
        ) or self.action_url is not None


def stream_identity(
    stream: AioStreamsStream,
    *,
    media_type: str,
    media_id: str,
) -> StreamIdentity:
    """Return safe server-side identity data for an AIOStreams stream."""
    magnet = _magnet_url(stream.url)
    info_hash = _normalized_info_hash(stream.info_hash) or _info_hash_from_magnet(magnet)
    if magnet is None and info_hash is not None:
        magnet = f"magnet:?xt=urn:btih:{info_hash}"

    return StreamIdentity(
        stream_key=_stream_key(stream, media_type=media_type, media_id=media_id),
        info_hash=info_hash,
        magnet=magnet,
        action_url=_action_url(stream),
    )


def find_stream_by_key(
    streams: tuple[AioStreamsStream, ...],
    *,
    media_type: str,
    media_id: str,
    stream_key: str,
) -> AioStreamsStream | None:
    for stream in streams:
        identity = stream_identity(stream, media_type=media_type, media_id=media_id)
        if identity.stream_key == stream_key:
            return stream
    return None


def stream_display_name(stream: AioStreamsStream) -> str:
    filename = stream.behavior_hints.get("filename")
    if isinstance(filename, str) and filename.strip():
        return filename.strip()
    if stream.title is not None:
        return stream.title.strip()
    if stream.name is not None:
        return stream.name.strip()
    return "Strmline selected stream"


def _stream_key(stream: AioStreamsStream, *, media_type: str, media_id: str) -> str:
    filename = stream.behavior_hints.get("filename")
    video_size = stream.behavior_hints.get("videoSize")
    material = {
        "file_idx": stream.file_idx,
        "filename": filename if isinstance(filename, str) else None,
        "info_hash": _normalized_info_hash(stream.info_hash),
        "media_id": media_id,
        "media_type": media_type,
        "name": stream.name,
        "title": stream.title,
        "video_size": video_size if isinstance(video_size, int) else None,
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:STREAM_KEY_LENGTH]


def _magnet_url(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urlparse(value)
    if parsed.scheme.casefold() != "magnet":
        return None
    return value


def _action_url(stream: AioStreamsStream) -> str | None:
    if stream.url is None or _magnet_url(stream.url) is not None:
        return None
    parsed = urlparse(stream.url)
    if parsed.scheme.casefold() not in {"http", "https"}:
        return None
    if not _looks_like_torbox_action_stream(stream):
        return None
    return stream.url


def _looks_like_torbox_action_stream(stream: AioStreamsStream) -> bool:
    combined = " ".join(
        field
        for field in (stream.name, stream.title, stream.description)
        if field is not None and field.strip()
    ).casefold()
    return any(
        marker in combined
        for marker in (
            "[tb",
            "instant tb",
            "cast (tb",
            "dl with tb",
            "torbox",
        )
    )


def _info_hash_from_magnet(magnet: str | None) -> str | None:
    if magnet is None:
        return None
    parsed = urlparse(magnet)
    query = parse_qs(parsed.query)
    for xt in query.get("xt", []):
        if xt.casefold().startswith("urn:btih:"):
            return _normalized_info_hash(xt.split(":", maxsplit=2)[-1])
    return None


def _normalized_info_hash(value: object) -> str | None:
    return normalize_info_hash(value)
