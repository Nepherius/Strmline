from pathlib import Path
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    GeneratedFile,
    LibraryEntry,
    MediaItem,
    SyncError,
    SyncRun,
    TorBoxItem,
    TorBoxStoredFile,
    utc_now,
)
from app.db.repositories.sync_runs import SyncRunRepository
from app.db.repositories.sync_state import SyncLibraryStateRepository
from app.sync.torbox_strm import SyncDiagnostic, SyncedStrmFile, TorBoxStrmSyncResult


class FakeResult:
    def __init__(self, scalar: object | None = None, scalars: list[object] | None = None) -> None:
        self._scalar = scalar
        self._scalars = scalars or []

    def scalar_one_or_none(self) -> object | None:
        return self._scalar

    def scalars(self) -> list[object]:
        return self._scalars

    def all(self) -> list[object]:
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

    def add_all(self, instances: list[object]) -> None:
        self.added.extend(instances)

    async def flush(self) -> None:
        for instance in self.added:
            if isinstance(
                instance,
                (
                    GeneratedFile,
                    LibraryEntry,
                    MediaItem,
                    SyncError,
                    SyncRun,
                    TorBoxItem,
                    TorBoxStoredFile,
                ),
            ):
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
    session = FakeSession([FakeResult() for _ in range(12)])
    library_root = _resolved(tmp_path)

    await SyncLibraryStateRepository(cast(AsyncSession, session)).persist_result(
        result,
        library_root,
    )

    assert session.committed is False
    assert not any(isinstance(item, SyncRun) for item in session.added)
    assert any(isinstance(item, MediaItem) for item in session.added)
    assert any(isinstance(item, LibraryEntry) for item in session.added)
    assert any(isinstance(item, TorBoxItem) for item in session.added)
    assert any(isinstance(item, TorBoxStoredFile) for item in session.added)
    generated_file = next(item for item in session.added if isinstance(item, GeneratedFile))
    assert generated_file.relative_path == "movies/Movie Name (2024)/Movie Name (2024).strm"
    assert generated_file.content_hash == "abc123"


@pytest.mark.asyncio
async def test_sync_run_repository_records_successful_runs(tmp_path: Path) -> None:
    session = FakeSession([])

    sync_run_id = await SyncRunRepository(cast(AsyncSession, session)).record_success(
        _sync_result(tmp_path)
    )

    assert sync_run_id == 1
    sync_run = next(item for item in session.added if isinstance(item, SyncRun))
    assert sync_run.status == "success"
    assert sync_run.source == "manual"
    assert sync_run.finished_at is not None
    assert sync_run.started_at <= sync_run.finished_at


@pytest.mark.asyncio
async def test_sync_run_repository_records_unmatched_media_as_dismissible_error(
    tmp_path: Path,
) -> None:
    session = FakeSession([])
    result = _sync_result(tmp_path)
    result = TorBoxStrmSyncResult(
        scanned_files=result.scanned_files,
        written_files=result.written_files,
        skipped_files=result.skipped_files,
        written_paths=result.written_paths,
        synced_files=result.synced_files,
        diagnostics=(
            SyncDiagnostic(
                phase="metadata_match",
                item_ref="Kaijuu 8 gou",
                message="No confident TMDB match was found.",
            ),
        ),
    )

    sync_run_id = await SyncRunRepository(cast(AsyncSession, session)).record_success(result)

    sync_run = next(item for item in session.added if isinstance(item, SyncRun))
    sync_error = next(item for item in session.added if isinstance(item, SyncError))
    assert sync_run.status == "partial"
    assert sync_error.sync_run_id == sync_run_id
    assert sync_error.phase == "metadata_match"
    assert sync_error.item_ref == "Kaijuu 8 gou"


@pytest.mark.asyncio
async def test_sync_state_repository_records_failed_runs() -> None:
    session = FakeSession([])

    sync_run_id = await SyncRunRepository(cast(AsyncSession, session)).record_failure(
        phase="torbox_sync",
        message="TorBox request failed with status 503.",
    )

    assert sync_run_id == 1
    assert session.committed is False
    sync_run = next(item for item in session.added if isinstance(item, SyncRun))
    sync_error = next(item for item in session.added if isinstance(item, SyncError))
    assert sync_run.status == "failed"
    assert sync_run.source == "manual"
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
        source="auto",
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
    session = FakeSession(
        [FakeResult(scalar=sync_run), FakeResult(scalar=sync_run), FakeResult(scalars=[sync_error])]
    )

    status = await SyncRunRepository(cast(AsyncSession, session)).status()

    assert status.last_run is not None
    assert status.last_run.id == 8
    assert status.last_run.status == "failed"
    assert status.last_run.source == "auto"
    assert status.last_run.skipped_count == 1
    assert status.last_auto_run is not None
    assert status.last_auto_run.id == 8
    assert len(status.recent_errors) == 1
    assert status.recent_errors[0].message == "TorBox request failed with status 503."


@pytest.mark.asyncio
async def test_sync_state_repository_dismisses_sync_errors() -> None:
    sync_error = SyncError(
        id=9,
        sync_run_id=8,
        phase="torbox_sync",
        message="TorBox request failed with status 503.",
        created_at=utc_now(),
    )
    session = FakeSession([FakeResult(scalar=sync_error)])

    dismissed = await SyncRunRepository(cast(AsyncSession, session)).dismiss_error(9)

    assert dismissed is True
    assert sync_error.dismissed_at is not None
    assert session.committed is False


@pytest.mark.asyncio
async def test_sync_state_repository_reports_missing_dismissed_error() -> None:
    session = FakeSession([FakeResult()])

    dismissed = await SyncRunRepository(cast(AsyncSession, session)).dismiss_error(404)

    assert dismissed is False
    assert session.committed is False


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
        [
            FakeResult(),
            FakeResult(),
            FakeResult(),
            FakeResult(),
            FakeResult(),
            FakeResult(),
            FakeResult(),
            FakeResult(),
            FakeResult(scalars=[stale_record]),
            FakeResult(scalars=[]),
            FakeResult(scalars=[]),
            FakeResult(scalars=[]),
        ]
    )

    await SyncLibraryStateRepository(cast(AsyncSession, session)).persist_result(
        result,
        _resolved(tmp_path),
    )

    assert stale_file.exists() is True
    assert session.deleted == [stale_record]


@pytest.mark.asyncio
async def test_sync_state_repository_keeps_stale_files_for_partial_runs(tmp_path: Path) -> None:
    stale_file = tmp_path / "movies" / "Old Movie (2023)" / "Old Movie (2023).strm"
    stale_file.parent.mkdir(parents=True)
    _ = stale_file.write_text("http://old.example\n", encoding="utf-8")
    result = _sync_result(tmp_path, partial=True)
    session = FakeSession([FakeResult() for _ in range(9)])

    await SyncLibraryStateRepository(cast(AsyncSession, session)).persist_result(
        result,
        _resolved(tmp_path),
    )

    assert stale_file.exists() is True


@pytest.mark.asyncio
async def test_sync_state_repository_keeps_selected_hash_when_torbox_source_is_absent(
    tmp_path: Path,
) -> None:
    virtual_file = tmp_path / "movies" / "Saved Movie (2024)" / "Saved Movie (2024).strm"
    virtual_file.parent.mkdir(parents=True)
    _ = virtual_file.write_text("http://strmline/play/saved\n", encoding="utf-8")
    virtual_record = GeneratedFile(
        id=8,
        library_entry_id=7,
        relative_path="movies/Saved Movie (2024)/Saved Movie (2024).strm",
        content_hash="saved-hash",
    )
    result = TorBoxStrmSyncResult(0, 0, 0, (), ())
    session = FakeSession(
        [
            FakeResult(scalars=[virtual_record.relative_path]),
            FakeResult(scalars=[virtual_record]),
            FakeResult(scalars=[]),
            FakeResult(scalars=[]),
            FakeResult(scalars=[]),
        ]
    )

    await SyncLibraryStateRepository(cast(AsyncSession, session)).persist_result(
        result,
        _resolved(tmp_path),
        retained_info_hashes=frozenset({"abc123"}),
    )

    assert virtual_file.exists() is True
    assert virtual_record not in session.deleted


@pytest.mark.asyncio
async def test_sync_state_repository_returns_retained_library_paths(tmp_path: Path) -> None:
    relative_path = "movies/Saved Movie (2024)/Saved Movie (2024).strm"
    session = FakeSession([FakeResult(scalars=[relative_path])])

    paths = await SyncLibraryStateRepository(cast(AsyncSession, session)).retained_library_paths(
        _resolved(tmp_path),
        frozenset({"abc123"}),
    )

    assert paths == {(tmp_path / relative_path).resolve(strict=False)}


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
