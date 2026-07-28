from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from time import monotonic

DEFAULT_TTL_SECONDS = 300.0
DEFAULT_MAX_ENTRIES = 256


@dataclass(frozen=True, slots=True)
class _CachedStreams[StreamValue]:
    streams: tuple[StreamValue, ...]
    expires_at: float


class AioStreamsResultCache[StreamValue]:
    """Small process-local cache for recently displayed stream results."""

    def __init__(
        self,
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if ttl_seconds <= 0 or max_entries <= 0:
            msg = "AIOStreams cache limits must be positive."
            raise ValueError(msg)
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._lock = Lock()
        self._entries: OrderedDict[str, _CachedStreams[StreamValue]] = OrderedDict()

    def get(self, key: str) -> tuple[StreamValue, ...] | None:
        with self._lock:
            cached = self._entries.get(key)
            if cached is None:
                return None
            if cached.expires_at <= self._clock():
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return cached.streams

    def put(self, key: str, streams: tuple[StreamValue, ...]) -> None:
        with self._lock:
            self._entries[key] = _CachedStreams(
                streams=streams,
                expires_at=self._clock() + self._ttl_seconds,
            )
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                _ = self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_result_cache = AioStreamsResultCache[object]()


def get_aiostreams_result_cache() -> AioStreamsResultCache[object]:
    return _result_cache


def clear_aiostreams_result_cache() -> None:
    _result_cache.clear()
