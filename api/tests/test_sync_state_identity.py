from pathlib import Path
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    GeneratedFile,
    LibraryEntry,
    MediaItem,
    SyncRun,
    TorBoxItem,
    TorBoxStoredFile,
)
from app.db.repositories.sync_state import SyncStateRepository
from app.sync.torbox_strm import SyncedStrmFile, TorBoxStrmSyncResult


class FakeResult:
    def __init__(self, scalar: object | None = None, values: list[object] | None = None) -> None:
        self._scalar = scalar
        self._values = values or []

    def scalar_one_or_none(self) -> object | None:
        return self._scalar

    def scalars(self) -> list[object]:
        return self._values

    def all(self) -> list[object]:
        return self._values


class FakeSession:
    def __init__(self, results: list[FakeResult]) -> None:
        self._results = results
        self.added: list[object] = []
        self._next_id = 1

    async def execute(self, statement: object) -> FakeResult:
        _ = statement
        return self._results.pop(0)

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        for instance in self.added:
            if isinstance(
                instance,
                (GeneratedFile, LibraryEntry, MediaItem, SyncRun, TorBoxItem, TorBoxStoredFile),
            ):
                instance.id = instance.id or self._next_id
                self._next_id += 1

    async def commit(self) -> None:
        pass

    async def delete(self, instance: object) -> None:
        _ = instance


@pytest.mark.asyncio
async def test_sync_corrects_existing_tmdb_media_category(tmp_path: Path) -> None:
    existing_item = MediaItem(
        id=10,
        media_type="movies",
        title="Ascendance of a Bookworm 01 JP BD Hi10",
        year=None,
        tmdb_id="91768",
    )
    output_path = tmp_path / "anime" / "Ascendance of a Bookworm" / "Season 01" / "S01E01.strm"
    synced_file = SyncedStrmFile(
        path=output_path,
        entry_id="entry-id",
        category="anime",
        title="Ascendance of a Bookworm",
        year=2019,
        season_number=1,
        episode_number=1,
        provider="torrents",
        provider_item_id="1",
        provider_file_id="2",
        content_hash="content-hash",
        tmdb_id="91768",
    )
    result = TorBoxStrmSyncResult(1, 1, 0, (output_path,), (synced_file,))
    session = FakeSession(
        [
            FakeResult(existing_item),
            *[FakeResult() for _ in range(4)],
            *[FakeResult(values=[]) for _ in range(3)],
        ]
    )

    _ = await SyncStateRepository(cast(AsyncSession, session)).record_success(result, tmp_path)

    assert existing_item.media_type == "anime"
    assert existing_item.title == "Ascendance of a Bookworm"
    assert existing_item.year == 2019
