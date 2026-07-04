from pathlib import Path
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GeneratedFile, LibraryEntry, MediaItem, SyncRun
from app.db.repositories.sync_state import SyncStateRepository
from app.sync.torbox_strm import SyncedStrmFile, TorBoxStrmSyncResult


class FakeResult:
    def __init__(self, scalar: object | None = None) -> None:
        self._scalar = scalar

    def scalar_one_or_none(self) -> object | None:
        return self._scalar


class FakeSession:
    def __init__(self, results: list[FakeResult]) -> None:
        self._results = results
        self.added: list[object] = []
        self.committed = False
        self._next_id = 1

    async def execute(self, statement: object) -> FakeResult:
        _ = statement
        return self._results.pop(0)

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        for instance in self.added:
            if isinstance(instance, (GeneratedFile, LibraryEntry, MediaItem, SyncRun)):
                instance.id = instance.id or self._next_id
                self._next_id += 1

    async def commit(self) -> None:
        self.committed = True


@pytest.mark.asyncio
async def test_sync_state_repository_records_generated_library_state(tmp_path: Path) -> None:
    written_path = tmp_path / "movies" / "Movie Name (2024)" / "Movie Name (2024).strm"
    written_path.parent.mkdir(parents=True)
    _ = written_path.write_text("http://strmline/play/id?token=token\n", encoding="utf-8")
    result = TorBoxStrmSyncResult(
        scanned_files=1,
        written_files=1,
        skipped_files=2,
        written_paths=(written_path.resolve(strict=False),),
        synced_files=(
            SyncedStrmFile(
                path=written_path.resolve(strict=False),
                entry_id="entry-id",
                category="movies",
                title="Movie Name",
                year=2024,
                season_number=None,
                episode_number=None,
                provider="torbox",
                provider_item_id="1",
                provider_file_id="2",
                content_hash="abc123",
            ),
        ),
    )
    session = FakeSession([FakeResult(), FakeResult(), FakeResult()])
    library_root = _resolved(tmp_path)

    sync_run_id = await SyncStateRepository(cast(AsyncSession, session)).record_success(
        result,
        library_root,
    )

    assert sync_run_id == 1
    assert session.committed is True
    assert any(isinstance(item, SyncRun) for item in session.added)
    assert any(isinstance(item, MediaItem) for item in session.added)
    assert any(isinstance(item, LibraryEntry) for item in session.added)
    generated_file = next(item for item in session.added if isinstance(item, GeneratedFile))
    assert generated_file.relative_path == "movies/Movie Name (2024)/Movie Name (2024).strm"
    assert generated_file.content_hash == "abc123"


def _resolved(path: Path) -> Path:
    return path.resolve(strict=False)
