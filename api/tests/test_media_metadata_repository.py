from __future__ import annotations

import pytest

from app.db.models import MediaItem
from app.db.repositories.media_metadata import MediaMetadataRepository


class FakeResult:
    def __init__(self, rows: list[tuple[object, object]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[object, object]]:
        return self._rows


class FakeSession:
    def __init__(self, rows: list[tuple[object, object]]) -> None:
        self._rows = rows

    async def execute(self, _statement: object) -> FakeResult:
        return FakeResult(self._rows)


@pytest.mark.asyncio
async def test_media_metadata_repository_requires_one_media_item() -> None:
    first = MediaItem(media_type="shows", title="From", year=None, tmdb_id="1")
    first.id = 1
    second = MediaItem(media_type="shows", title="From", year=None, tmdb_id="2")
    second.id = 2

    single = await MediaMetadataRepository(
        FakeSession([(first, "shows/From/Season 01/From - S01E01.strm")])  # type: ignore[arg-type]
    ).find_for_library_prefix("shows/From")
    multiple = await MediaMetadataRepository(
        FakeSession(
            [
                (first, "shows/From/Season 01/From - S01E01.strm"),
                (second, "shows/From/Season 02/From - S02E01.strm"),
            ]
        )  # type: ignore[arg-type]
    ).find_for_library_prefix("shows/From")

    assert single is not None
    assert single.media_item is first
    assert multiple is None


@pytest.mark.asyncio
async def test_media_metadata_repository_maps_generated_files_to_entry_prefixes() -> None:
    movie = MediaItem(media_type="movies", title="Always", year=2011, tmdb_id="1")
    movie.id = 1
    show = MediaItem(media_type="shows", title="From", year=None, tmdb_id="2")
    show.id = 2
    repository = MediaMetadataRepository(
        FakeSession(
            [
                ("movies/Always (2011)/Always (2011).strm", "1"),
                ("shows/From/Season 01/From - S01E01.strm", "2"),
            ]
        )  # type: ignore[arg-type]
    )

    tmdb_ids = await repository.tmdb_ids_for_library_prefixes(
        {"movies/Always (2011)", "shows/From", "anime/Missing"}
    )

    assert tmdb_ids == {"movies/Always (2011)": "1", "shows/From": "2"}
