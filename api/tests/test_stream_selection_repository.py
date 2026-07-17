from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import StreamSelection
from app.db.repositories.stream_selection import (
    StreamSelectionRepository,
    StreamSelectionWrite,
)


class FakeResult:
    def __init__(self, selection: StreamSelection | None) -> None:
        self.selection = selection

    def scalar_one_or_none(self) -> StreamSelection | None:
        return self.selection


class FakeSession:
    def __init__(self, selection: StreamSelection) -> None:
        self.selection = selection
        self.flushes = 0

    async def execute(self, statement: object) -> FakeResult:
        _ = statement
        return FakeResult(self.selection)

    async def flush(self) -> None:
        self.flushes += 1


@pytest.mark.asyncio
async def test_upsert_never_replaces_a_search_confirmed_identity() -> None:
    selection = StreamSelection(
        stream_key="stream-key",
        media_type="series",
        media_id="tt-search-confirmed:1:1",
        tmdb_id="91768",
        media_title="Ascendance of a Bookworm",
        media_year=2019,
        identity_authority="search_confirmed",
        title="Bookworm release",
        info_hash="ab" * 20,
        status="selected",
    )
    session = FakeSession(selection)
    repository = StreamSelectionRepository(cast(AsyncSession, session))

    record = await repository.upsert(
        StreamSelectionWrite(
            stream_key="stream-key",
            media_type="movie",
            media_id="tt-wrong",
            tmdb_id="99999",
            media_title="Wrong Match",
            media_year=2024,
            title="Updated release name",
            source_name="source",
            info_hash="CD" * 20,
            torbox_torrent_id="42",
        )
    )

    assert (record.media_type, record.media_id) == ("series", "tt-search-confirmed:1:1")
    assert (record.tmdb_id, record.media_title, record.media_year) == (
        "91768",
        "Ascendance of a Bookworm",
        2019,
    )
    assert record.title == "Updated release name"
    assert record.info_hash == "cd" * 20
    assert session.flushes == 1


@pytest.mark.asyncio
async def test_resolver_update_only_fills_a_missing_identity() -> None:
    selection = StreamSelection(
        stream_key="stream-key",
        media_type="series",
        media_id="tt-search-confirmed",
        tmdb_id="91768",
        media_title="Ascendance of a Bookworm",
        media_year=2019,
        identity_authority="search_confirmed",
        title="release",
        status="selected",
    )
    session = FakeSession(selection)
    repository = StreamSelectionRepository(cast(AsyncSession, session))

    await repository.update_media_identity(
        "stream-key",
        tmdb_id="99999",
        media_title="Wrong Match",
        media_year=2024,
        media_poster_path=None,
    )

    assert (selection.tmdb_id, selection.media_title, selection.media_year) == (
        "91768",
        "Ascendance of a Bookworm",
        2019,
    )
    assert session.flushes == 0
