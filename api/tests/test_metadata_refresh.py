from __future__ import annotations

from pathlib import Path

import pytest

from app.db.models import MediaItem
from app.db.repositories.media_metadata import LibraryMediaRecord
from app.library import metadata_refresh
from app.library.posters import PosterImage


class FakeSession:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True


class FakePosterFetcher:
    async def fetch(self, poster_path: str) -> PosterImage:
        assert poster_path == "/new-poster.jpg"
        return PosterImage(content=b"poster", suffix=".jpg")


class FakeTmdbClient:
    async def get_json(self, endpoint: str) -> dict[str, object]:
        assert endpoint == "/tv/91768"
        return {
            "name": "Ascendance of a Bookworm",
            "first_air_date": "2019-10-03",
            "poster_path": "/new-poster.jpg",
        }


@pytest.mark.asyncio
async def test_refresh_library_metadata_replaces_artwork_and_updates_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media_item = MediaItem(media_type="shows", title="Old title", year=None, tmdb_id="91768")
    media_item.id = 1
    session = FakeSession()
    stored: list[dict[str, object]] = []

    class FakeMediaRepository:
        def __init__(self, _session: object) -> None:
            pass

        async def find_for_library_prefix(self, relative_prefix: str) -> LibraryMediaRecord:
            assert relative_prefix == "shows/Ascendance of a Bookworm"
            return LibraryMediaRecord(media_item=media_item)

    class FakeCacheRepository:
        def __init__(self, _session: object) -> None:
            pass

        async def store(self, **kwargs: object) -> None:
            stored.append(kwargs)

    monkeypatch.setattr(metadata_refresh, "MediaMetadataRepository", FakeMediaRepository)
    monkeypatch.setattr(metadata_refresh, "TmdbCacheRepository", FakeCacheRepository)

    refreshed = await metadata_refresh.refresh_library_metadata(
        session,  # type: ignore[arg-type]
        library_root=tmp_path,
        relative_prefix="shows/Ascendance of a Bookworm",
        tmdb_client=FakeTmdbClient(),  # type: ignore[arg-type]
        poster_fetcher=FakePosterFetcher(),
    )

    assert refreshed == 1
    assert media_item.title == "Ascendance of a Bookworm"
    assert media_item.year == 2019
    assert (tmp_path / "artwork" / "tmdb-91768" / "poster.jpg").read_bytes() == b"poster"
    assert stored[0]["endpoint"] == "/tv/91768"
    assert session.committed is True
