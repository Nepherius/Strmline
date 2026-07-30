from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from time import monotonic

from app.providers.torbox.manifests import TorBoxTorrentManifest

DEFAULT_TTL_SECONDS = 300.0
DEFAULT_NEGATIVE_TTL_SECONDS = 30.0
DEFAULT_MAX_ENTRIES = 512


@dataclass(frozen=True, slots=True)
class _CachedManifest:
    manifest: TorBoxTorrentManifest | None
    expires_at: float


class TorBoxManifestCache:
    def __init__(
        self,
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        negative_ttl_seconds: float = DEFAULT_NEGATIVE_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if ttl_seconds <= 0 or negative_ttl_seconds <= 0 or max_entries <= 0:
            msg = "TorBox manifest cache limits must be positive."
            raise ValueError(msg)
        self._ttl_seconds = ttl_seconds
        self._negative_ttl_seconds = negative_ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._lock = Lock()
        self._entries: OrderedDict[str, _CachedManifest] = OrderedDict()

    def get(self, key: str) -> tuple[bool, TorBoxTorrentManifest | None]:
        with self._lock:
            cached = self._entries.get(key)
            if cached is None:
                return False, None
            if cached.expires_at <= self._clock():
                del self._entries[key]
                return False, None
            self._entries.move_to_end(key)
            return True, cached.manifest

    def put(self, key: str, manifest: TorBoxTorrentManifest | None) -> None:
        ttl = self._ttl_seconds if manifest is not None else self._negative_ttl_seconds
        with self._lock:
            self._entries[key] = _CachedManifest(
                manifest=manifest,
                expires_at=self._clock() + ttl,
            )
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                _ = self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_manifest_cache = TorBoxManifestCache()


def get_torbox_manifest_cache() -> TorBoxManifestCache:
    return _manifest_cache


def clear_torbox_manifest_cache() -> None:
    _manifest_cache.clear()
