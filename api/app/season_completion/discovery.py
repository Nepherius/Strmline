from __future__ import annotations

import asyncio
import hashlib
import re
from collections import defaultdict
from time import monotonic
from typing import Protocol

from app.providers.aiostreams.client import AioStreamsStream
from app.search.stream_identity import StreamIdentity, stream_identity
from app.season_completion.ranking import CompletionCandidate, EpisodeRef, release_family

MAX_CONCURRENT_SEARCHES = 4
MIN_AIOSTREAMS_REQUEST_INTERVAL_SECONDS = 2.0
EPISODE_IN_LABEL = re.compile(r"(?i)(?:[ ._-]*(?:e|ep)\d{1,3})+")
PACK_TOTAL_SIZE = re.compile(r"/\s*(\d+(?:\.\d+)?)\s*([kmgt])b\b", re.IGNORECASE)
SIZE_UNITS = {"k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}


class EpisodeStreamClient(Protocol):
    async def streams(
        self,
        *,
        media_type: str,
        media_id: str,
    ) -> tuple[AioStreamsStream, ...]: ...


class CacheStatusClient(Protocol):
    async def check_cached(self, hashes: list[str]) -> dict[str, bool]: ...


class AioStreamsRequestLimiter:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._last_request_at: float | None = None

    async def wait(self) -> None:
        async with self._lock:
            now = monotonic()
            if self._last_request_at is not None:
                delay = MIN_AIOSTREAMS_REQUEST_INTERVAL_SECONDS - (now - self._last_request_at)
                if delay > 0:
                    await asyncio.sleep(delay)
            self._last_request_at = monotonic()


async def discover_candidates(
    *,
    aiostreams_client: EpisodeStreamClient,
    torbox_client: CacheStatusClient,
    imdb_id: str,
    missing: frozenset[EpisodeRef],
    limiter: AioStreamsRequestLimiter | None = None,
) -> list[CompletionCandidate]:
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_SEARCHES)
    request_limiter = limiter or AioStreamsRequestLimiter()

    async def fetch(episode: EpisodeRef) -> tuple[EpisodeRef, tuple[AioStreamsStream, ...]]:
        async with semaphore:
            await request_limiter.wait()
            streams = await aiostreams_client.streams(
                media_type="series",
                media_id=f"{imdb_id}:{episode.season}:{episode.episode}",
            )
        return episode, streams

    results = dict(await asyncio.gather(*(fetch(episode) for episode in sorted(missing))))
    cached_by_hash = await torbox_client.check_cached(_stream_hashes(results))
    return group_stream_candidates(results, cached_by_hash=cached_by_hash)


def group_stream_candidates(
    streams_by_episode: dict[EpisodeRef, tuple[AioStreamsStream, ...]],
    *,
    cached_by_hash: dict[str, bool],
) -> list[CompletionCandidate]:
    grouped_episodes: dict[str, set[EpisodeRef]] = defaultdict(set)
    representatives: dict[str, tuple[AioStreamsStream, StreamIdentity]] = {}
    for episode, streams in streams_by_episode.items():
        for stream in streams:
            identity = stream_identity(
                stream,
                media_type="series",
                media_id=f"completion:{episode.season}:{episode.episode}",
            )
            source_id = _source_id(stream, identity)
            if source_id is None:
                continue
            grouped_episodes[source_id].add(episode)
            _ = representatives.setdefault(
                source_id,
                (stream, identity),
            )

    return [
        _candidate(
            source_id,
            *representatives[source_id],
            frozenset(episodes),
            cached=_cached(representatives[source_id][1], cached_by_hash),
        )
        for source_id, episodes in grouped_episodes.items()
    ]


def _candidate(
    source_id: str,
    stream: AioStreamsStream,
    identity: StreamIdentity,
    episodes: frozenset[EpisodeRef],
    *,
    cached: bool,
) -> CompletionCandidate:
    filename = stream.behavior_hints.get("filename")
    safe_filename = filename if isinstance(filename, str) else None
    title = safe_filename or stream.title or stream.name or source_id
    return CompletionCandidate(
        source_id=source_id,
        info_hash=identity.info_hash,
        action_url=identity.action_url,
        title=title,
        release_family=release_family(safe_filename or stream.title),
        episodes=episodes,
        cached=cached,
        match_labels=_match_labels(stream, safe_filename),
    )


def _stream_hashes(
    streams_by_episode: dict[EpisodeRef, tuple[AioStreamsStream, ...]],
) -> list[str]:
    hashes: set[str] = set()
    for episode, streams in streams_by_episode.items():
        for stream in streams:
            identity = stream_identity(
                stream,
                media_type="series",
                media_id=f"completion:{episode.season}:{episode.episode}",
            )
            if identity.info_hash is not None:
                hashes.add(identity.info_hash)
    return sorted(hashes)


def _source_id(stream: AioStreamsStream, identity: StreamIdentity) -> str | None:
    if identity.info_hash is not None:
        return f"hash:{identity.info_hash}"
    if identity.action_url is None or not _is_cached_action_stream(stream):
        return None
    return f"action:{_action_key(stream)}"


def _cached(identity: StreamIdentity, cached_by_hash: dict[str, bool]) -> bool:
    if identity.info_hash is not None:
        return cached_by_hash.get(identity.info_hash, False)
    return identity.action_url is not None


def _is_cached_action_stream(stream: AioStreamsStream) -> bool:
    label = " ".join(value for value in (stream.name, stream.title) if value).casefold()
    return "[tb\u26a1" in label or "[tb cached" in label


def _action_key(stream: AioStreamsStream) -> str:
    filename = stream.behavior_hints.get("filename")
    if _is_multi_file_pack(stream):
        binge_group = stream.behavior_hints.get("bingeGroup")
        material = "\0".join(
            value
            for value in (
                stream.name,
                binge_group if isinstance(binge_group, str) else None,
                _pack_label(stream),
            )
            if value
        )
    else:
        material = "\0".join(
            value
            for value in (
                stream.name,
                stream.title,
                filename if isinstance(filename, str) else None,
            )
            if value
        )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def _is_multi_file_pack(stream: AioStreamsStream) -> bool:
    video_size = stream.behavior_hints.get("videoSize")
    if not isinstance(video_size, int) or video_size <= 0 or stream.description is None:
        return False
    match = PACK_TOTAL_SIZE.search(stream.description)
    if match is None:
        return False
    total_size = float(match.group(1)) * SIZE_UNITS[match.group(2).casefold()]
    return total_size > video_size * 1.2


def _pack_label(stream: AioStreamsStream) -> str | None:
    label = _provider_folder_label(stream.description) or stream.title
    if label is None:
        return None
    return EPISODE_IN_LABEL.sub("", label).strip() or None


def _match_labels(stream: AioStreamsStream, filename: str | None) -> tuple[str, ...]:
    labels = [filename, stream.title, _provider_folder_label(stream.description)]
    return tuple(dict.fromkeys(label for label in labels if label))


def _provider_folder_label(description: str | None) -> str | None:
    if description is None:
        return None
    first_line = description.splitlines()[0].lstrip()
    while first_line and not first_line[0].isalnum():
        first_line = first_line[1:]
    return first_line or None
