import pytest

from app.resolver.target_cache import ResolvedTargetCache


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_resolved_target_cache_expires_without_persistence() -> None:
    clock = FakeClock()
    cache = ResolvedTargetCache(ttl_seconds=30, max_entries=2, clock=clock)

    cache.put("entry", "https://cdn.example.test/temporary")
    assert cache.get("entry") == "https://cdn.example.test/temporary"

    clock.now = 30
    assert cache.get("entry") is None


def test_resolved_target_cache_evicts_least_recently_used_entry() -> None:
    cache = ResolvedTargetCache(ttl_seconds=30, max_entries=2)
    cache.put("first", "https://cdn.example.test/first")
    cache.put("second", "https://cdn.example.test/second")
    assert cache.get("first") == "https://cdn.example.test/first"

    cache.put("third", "https://cdn.example.test/third")

    assert cache.get("first") == "https://cdn.example.test/first"
    assert cache.get("second") is None
    assert cache.get("third") == "https://cdn.example.test/third"


@pytest.mark.parametrize(
    ("ttl_seconds", "max_entries"),
    [(0, 1), (1, 0)],
)
def test_resolved_target_cache_rejects_unbounded_configuration(
    ttl_seconds: float,
    max_entries: int,
) -> None:
    with pytest.raises(ValueError, match=r"cache (TTL|size) must be positive"):
        _ = ResolvedTargetCache(ttl_seconds=ttl_seconds, max_entries=max_entries)
