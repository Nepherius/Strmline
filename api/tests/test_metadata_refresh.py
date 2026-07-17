from __future__ import annotations

from pathlib import Path

import pytest

from app.db.models import MediaExternalIdentity, MediaItem
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
        return PosterImage(content=b"\xff\xd8\xffposter", suffix=".jpg")


class FakeTmdbClient:
    async def get_json(self, endpoint: str) -> dict[str, object]:
        assert endpoint == "/tv/91768"
        return {
            "name": "Ascendance of a Bookworm",
            "first_air_date": "2019-10-03",
            "poster_path": "/new-poster.jpg",
        }


def _record(
    media_item: MediaItem,
    tmdb_id: str,
    *,
    provider_kind: str,
) -> LibraryMediaRecord:
    identity = MediaExternalIdentity(
        media_item_id=media_item.id,
        provider="tmdb",
        provider_media_kind=provider_kind,
        external_id=tmdb_id,
        authority="manual",
        authoritative=True,
    )
    return LibraryMediaRecord(media_item=media_item, tmdb_identity=identity)


@pytest.mark.asyncio
async def test_refresh_library_metadata_replaces_artwork_and_updates_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media_item = MediaItem(content_kind="series", title="Old title", year=None)
    media_item.id = 1
    session = FakeSession()
    stored: list[dict[str, object]] = []

    class FakeMediaRepository:
        def __init__(self, _session: object) -> None:
            pass

        async def find_for_media_item(self, media_item_id: int) -> LibraryMediaRecord:
            assert media_item_id == 1
            return _record(media_item, "91768", provider_kind="tv")

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
        media_item_id=1,
        tmdb_client=FakeTmdbClient(),  # type: ignore[arg-type]
        poster_fetcher=FakePosterFetcher(),
    )

    assert refreshed == 1
    assert media_item.title == "Ascendance of a Bookworm"
    assert media_item.year == 2019
    assert media_item.poster_path == "/new-poster.jpg"
    assert (tmp_path / "artwork" / "tmdb-91768" / "poster.jpg").read_bytes() == (
        b"\xff\xd8\xffposter"
    )
    assert stored[0]["endpoint"] == "/tv/91768"
    assert session.committed is False


@pytest.mark.asyncio
async def test_refresh_library_metadata_allows_identity_without_a_poster(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media_item = MediaItem(content_kind="movie", title="Old title", year=None)
    media_item.id = 1
    session = FakeSession()

    class FakeMediaRepository:
        def __init__(self, _session: object) -> None:
            pass

        async def find_for_media_item(self, _media_item_id: int) -> LibraryMediaRecord:
            return _record(media_item, "550", provider_kind="movie")

    class FakeCacheRepository:
        def __init__(self, _session: object) -> None:
            pass

        async def store(self, **_kwargs: object) -> None:
            return None

    class FakeTmdbClientWithoutPoster:
        async def get_json(self, endpoint: str) -> dict[str, object]:
            assert endpoint == "/movie/550"
            return {"title": "Fight Club", "release_date": "1999-10-15"}

    monkeypatch.setattr(metadata_refresh, "MediaMetadataRepository", FakeMediaRepository)
    monkeypatch.setattr(metadata_refresh, "TmdbCacheRepository", FakeCacheRepository)

    refreshed = await metadata_refresh.refresh_library_metadata(
        session,  # type: ignore[arg-type]
        library_root=tmp_path,
        media_item_id=1,
        tmdb_client=FakeTmdbClientWithoutPoster(),  # type: ignore[arg-type]
        poster_fetcher=FakePosterFetcher(),
        require_poster=False,
    )

    assert refreshed == 0
    assert media_item.title == "Fight Club"
    assert media_item.year == 1999
    assert session.committed is False
