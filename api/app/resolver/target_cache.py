from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic


@dataclass(frozen=True, slots=True)
class _CachedTarget:
    target_url: str
    expires_at: float


class ResolvedTargetCache:
    """Bounded process-memory cache for short-lived redirect targets.

    The cache stores only the resolved URL string. It never fetches, buffers, or
    persists any media response body, and all entries disappear on restart.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float,
        max_entries: int,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            msg = "Resolved target cache TTL must be positive."
            raise ValueError(msg)
        if max_entries <= 0:
            msg = "Resolved target cache size must be positive."
            raise ValueError(msg)
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[str, _CachedTarget] = OrderedDict()

    def get(self, entry_id: str) -> str | None:
        cached = self._entries.get(entry_id)
        if cached is None:
            return None
        if cached.expires_at <= self._clock():
            del self._entries[entry_id]
            return None
        self._entries.move_to_end(entry_id)
        return cached.target_url

    def put(self, entry_id: str, target_url: str) -> None:
        self._entries[entry_id] = _CachedTarget(
            target_url=target_url,
            expires_at=self._clock() + self._ttl_seconds,
        )
        self._entries.move_to_end(entry_id)
        while len(self._entries) > self._max_entries:
            _ = self._entries.popitem(last=False)

    def clear(self) -> None:
        self._entries.clear()
