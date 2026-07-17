from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from app.library.posters import (
    PosterImage,
    cache_missing_posters,
    poster_for_tmdb_id,
    refresh_posters,
)


@dataclass(frozen=True, slots=True)
class PosterSource:
    tmdb_id: str | None
    tmdb_poster_path: str | None


class FakePosterFetcher:
    def __init__(self) -> None:
        self.requests: list[str] = []

    async def fetch(self, poster_path: str) -> PosterImage:
        self.requests.append(poster_path)
        return PosterImage(content=b"\xff\xd8\xffposter", suffix=".jpg")


@pytest.mark.asyncio
async def test_poster_cache_skips_existing_artwork_without_fetching(tmp_path: Path) -> None:
    fetcher = FakePosterFetcher()
    source = PosterSource(tmdb_id="91768", tmdb_poster_path="/bookworm.jpg")

    first = await cache_missing_posters(tmp_path, (source,), fetcher)
    second = await cache_missing_posters(tmp_path, (source,), fetcher)

    poster = tmp_path / "artwork" / "tmdb-91768" / "poster.jpg"
    assert poster.read_bytes() == b"\xff\xd8\xffposter"
    assert first.downloaded == 1
    assert first.cached == 0
    assert second.downloaded == 0
    assert second.cached == 1
    assert fetcher.requests == ["/bookworm.jpg"]


@pytest.mark.asyncio
async def test_refresh_replaces_cached_artwork_for_tmdb_identity(tmp_path: Path) -> None:
    fetcher = FakePosterFetcher()
    artwork = tmp_path / "artwork" / "tmdb-91768"
    artwork.mkdir(parents=True)
    _ = (artwork / "poster.png").write_bytes(b"old")

    refreshed = await refresh_posters(tmp_path, fetcher, "/bookworm.jpg", "91768")

    poster = poster_for_tmdb_id(tmp_path, "91768")
    assert refreshed == 1
    assert poster is not None
    assert poster.name == "poster.jpg"
    assert poster.read_bytes() == b"\xff\xd8\xffposter"
    assert not (artwork / "poster.png").exists()


@pytest.mark.asyncio
async def test_corrupt_cached_artwork_is_replaced(tmp_path: Path) -> None:
    artwork = tmp_path / "artwork" / "tmdb-91768"
    artwork.mkdir(parents=True)
    _ = (artwork / "poster.jpg").write_bytes(b"not-an-image")
    fetcher = FakePosterFetcher()

    result = await cache_missing_posters(
        tmp_path,
        (PosterSource(tmdb_id="91768", tmdb_poster_path="/bookworm.jpg"),),
        fetcher,
    )

    assert result.downloaded == 1
    assert result.cached == 0
    assert (artwork / "poster.jpg").read_bytes() == b"\xff\xd8\xffposter"
