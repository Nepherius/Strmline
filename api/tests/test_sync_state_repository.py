from pathlib import Path
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GeneratedFile, LibraryEntry, MediaItem, SyncError, SyncRun, utc_now
from app.db.repositories.sync_state import SyncStateRepository
from app.sync.torbox_strm import SyncedStrmFile, TorBoxStrmSyncResult


class FakeResult:
    def __init__(self, scalar: object | None = None, scalars: list[object] | None = None) -> None:
        self._scalar = scalar
        self._scalars = scalars or []

    def scalar_one_or_none(self) -> object | None:
        return self._scalar

    def scalars(self) -> list[object]:
        return self._scalars


class FakeSession:
    def __init__(self, results: list[FakeResult]) -> None:
        self._results = results
        self.added: list[object] = []
        self.deleted: list[object] = []
        self.committed = False
        self._next_id = 1

    async def execute(self, statement: object) -> FakeResult:
        _ = statement
        return self._results.pop(0)

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        for instance in self.added:
            if isinstance(instance, (GeneratedFile, LibraryEntry, MediaItem, SyncError, SyncRun)):
                instance.id = instance.id or self._next_id
                self._next_id += 1

    async def commit(self) -> None:
        self.committed = True

    async def delete(self, instance: object) -> None:
        self.deleted.append(instance)


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
    session = FakeSession([FakeResult(), FakeResult(), FakeResult(), FakeResult(scalars=[])])
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
    sync_run = next(item for item in session.added if isinstance(item, SyncRun))
    assert sync_run.status == "success"
    assert sync_run.finished_at is not None
    assert sync_run.started_at <= sync_run.finished_at


@pytest.mark.asyncio
async def test_sync_state_repository_records_failed_runs() -> None:
    session = FakeSession([])

    sync_run_id = await SyncStateRepository(cast(AsyncSession, session)).record_failure(
        phase="torbox_sync",
        message="TorBox request failed with status 503.",
    )

    assert sync_run_id == 1
    assert session.committed is True
    sync_run = next(item for item in session.added if isinstance(item, SyncRun))
    sync_error = next(item for item in session.added if isinstance(item, SyncError))
    assert sync_run.status == "failed"
    assert sync_run.finished_at is not None
    assert sync_run.started_at <= sync_run.finished_at
    assert sync_error.sync_run_id == sync_run_id
    assert sync_error.phase == "torbox_sync"
    assert sync_error.message == "TorBox request failed with status 503."


@pytest.mark.asyncio
async def test_sync_state_repository_reads_latest_status() -> None:
    started_at = utc_now()
    sync_run = SyncRun(
        id=8,
        status="failed",
        started_at=started_at,
        finished_at=started_at,
        scanned_count=3,
        written_count=2,
        skipped_count=1,
    )
    sync_error = SyncError(
        id=9,
        sync_run_id=8,
        phase="torbox_sync",
        message="TorBox request failed with status 503.",
        created_at=started_at,
    )
    session = FakeSession([FakeResult(scalar=sync_run), FakeResult(scalars=[sync_error])])

    status = await SyncStateRepository(cast(AsyncSession, session)).status()

    assert status.last_run is not None
    assert status.last_run.id == 8
    assert status.last_run.status == "failed"
    assert status.last_run.skipped_count == 1
    assert len(status.recent_errors) == 1
    assert status.recent_errors[0].message == "TorBox request failed with status 503."


@pytest.mark.asyncio
async def test_sync_state_repository_removes_stale_generated_files(tmp_path: Path) -> None:
    stale_file = tmp_path / "movies" / "Old Movie (2023)" / "Old Movie (2023).strm"
    stale_file.parent.mkdir(parents=True)
    _ = stale_file.write_text("http://old.example\n", encoding="utf-8")
    stale_record = GeneratedFile(
        library_entry_id=99,
        relative_path="movies/Old Movie (2023)/Old Movie (2023).strm",
        content_hash="old",
    )
    result = _sync_result(tmp_path)
    session = FakeSession(
        [FakeResult(), FakeResult(), FakeResult(), FakeResult(scalars=[stale_record])]
    )

    _ = await SyncStateRepository(cast(AsyncSession, session)).record_success(
        result,
        _resolved(tmp_path),
    )

    assert stale_file.exists() is False
    assert session.deleted == [stale_record]


@pytest.mark.asyncio
async def test_sync_state_repository_keeps_stale_files_for_partial_runs(tmp_path: Path) -> None:
    stale_file = tmp_path / "movies" / "Old Movie (2023)" / "Old Movie (2023).strm"
    stale_file.parent.mkdir(parents=True)
    _ = stale_file.write_text("http://old.example\n", encoding="utf-8")
    result = _sync_result(tmp_path, partial=True)
    session = FakeSession([FakeResult(), FakeResult(), FakeResult()])

    _ = await SyncStateRepository(cast(AsyncSession, session)).record_success(
        result,
        _resolved(tmp_path),
    )

    assert stale_file.exists() is True
    assert session.deleted == []


def _resolved(path: Path) -> Path:
    return path.resolve(strict=False)


def _sync_result(tmp_path: Path, *, partial: bool = False) -> TorBoxStrmSyncResult:
    written_path = tmp_path / "movies" / "Movie Name (2024)" / "Movie Name (2024).strm"
    written_path.parent.mkdir(parents=True, exist_ok=True)
    _ = written_path.write_text("http://strmline/play/id?token=token\n", encoding="utf-8")
    return TorBoxStrmSyncResult(
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
        partial=partial,
    )
