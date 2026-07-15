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
    session = FakeSession([FakeResult() for _ in range(8)])
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
    assert any(isinstance(item, TorBoxItem) for item in session.added)
    assert any(isinstance(item, TorBoxStoredFile) for item in session.added)
    generated_file = next(item for item in session.added if isinstance(item, GeneratedFile))
    assert generated_file.relative_path == "movies/Movie Name (2024)/Movie Name (2024).strm"
    assert generated_file.content_hash == "abc123"
    sync_run = next(item for item in session.added if isinstance(item, SyncRun))
    assert sync_run.status == "success"
    assert sync_run.source == "manual"
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

    status = await SyncStateRepository(cast(AsyncSession, session)).status()

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

    dismissed = await SyncStateRepository(cast(AsyncSession, session)).dismiss_error(9)

    assert dismissed is True
    assert sync_error.dismissed_at is not None
    assert session.committed is True


@pytest.mark.asyncio
async def test_sync_state_repository_reports_missing_dismissed_error() -> None:
    session = FakeSession([FakeResult()])

    dismissed = await SyncStateRepository(cast(AsyncSession, session)).dismiss_error(404)

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
            FakeResult(scalars=[stale_record]),
            FakeResult(scalars=[]),
            FakeResult(scalars=[]),
        ]
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
    session = FakeSession([FakeResult() for _ in range(5)])

    _ = await SyncStateRepository(cast(AsyncSession, session)).record_success(
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
        ]
    )

    _ = await SyncStateRepository(cast(AsyncSession, session)).record_success(
        result,
        _resolved(tmp_path),
        permanent_info_hashes=frozenset({"abc123"}),
    )

    assert virtual_file.exists() is True
    assert virtual_record not in session.deleted


@pytest.mark.asyncio
async def test_sync_state_repository_returns_permanent_library_paths(tmp_path: Path) -> None:
    relative_path = "movies/Saved Movie (2024)/Saved Movie (2024).strm"
    session = FakeSession([FakeResult(scalars=[relative_path])])

    paths = await SyncStateRepository(cast(AsyncSession, session)).permanent_library_paths(
        _resolved(tmp_path),
        frozenset({"abc123"}),
    )

    assert paths == {(tmp_path / relative_path).resolve(strict=False)}


@pytest.mark.asyncio
async def test_sync_state_repository_returns_all_permanent_hashes() -> None:
    session = FakeSession([FakeResult(scalars=["ABC123", None, "def456"])])

    hashes = await SyncStateRepository(cast(AsyncSession, session)).permanent_info_hashes()

    assert hashes == frozenset({"abc123", "def456"})
    assert session.deleted == []


@pytest.mark.asyncio
async def test_sync_state_repository_collapses_duplicates_by_tmdb_id(tmp_path: Path) -> None:
    # We will simulate syncing two files with different titles but the same tmdb_id.
    # The repository should retrieve the existing media item by tmdb_id and use it.

    file1 = tmp_path / "movies" / "Title One (2026)" / "Title One (2026).strm"
    file2 = tmp_path / "movies" / "Title Two (2026)" / "Title Two (2026).strm"
    file1.parent.mkdir(parents=True, exist_ok=True)
    file2.parent.mkdir(parents=True, exist_ok=True)
    _ = file1.write_text("url1", encoding="utf-8")
    _ = file2.write_text("url2", encoding="utf-8")

    result = TorBoxStrmSyncResult(
        scanned_files=2,
        written_files=2,
        skipped_files=0,
        written_paths=(file1.resolve(strict=False), file2.resolve(strict=False)),
        synced_files=(
            SyncedStrmFile(
                path=file1.resolve(strict=False),
                entry_id="entry-1",
                category="movies",
                title="Title One",
                year=2026,
                season_number=None,
                episode_number=None,
                provider="torbox",
                provider_item_id="1",
                provider_file_id="2",
                content_hash="hash1",
                tmdb_id="unique-tmdb-123",
            ),
            SyncedStrmFile(
                path=file2.resolve(strict=False),
                entry_id="entry-2",
                category="movies",
                title="Title Two",
                year=2026,
                season_number=None,
                episode_number=None,
                provider="torbox",
                provider_item_id="1",
                provider_file_id="3",
                content_hash="hash2",
                tmdb_id="unique-tmdb-123",
            ),
        ),
    )

    # 1st loop iteration:
    #   - get_media_item executes select by tmdb_id (return None)
    #   - get_media_item executes select by title+year (return None) -> MediaItem created
    #   - get_library_entry executes select by entry_id (return None) -> LibraryEntry created
    #   - get_generated_file executes select by path (return None) -> GeneratedFile created
    # 2nd loop iteration:
    #   - get_media_item executes select by tmdb_id (return existing MediaItem) -> Returns MediaItem
    #   - get_library_entry executes select by entry_id (return None) -> LibraryEntry created
    #   - get_generated_file executes select by path (return None) -> GeneratedFile created
    # 3rd block (cleanup): select GeneratedFile (empty)

    existing_item = MediaItem(
        media_type="movies",
        title="Title One",
        year=2026,
        tmdb_id="unique-tmdb-123",
    )

    session = FakeSession(
        [
            FakeResult(None),  # 1.1 tmdb_id check
            FakeResult(None),  # 1.2 title+year check
            FakeResult(None),  # 1.3 TorBox item
            FakeResult(None),  # 1.4 TorBox file
            FakeResult(None),  # 1.5 library entry
            FakeResult(None),  # 1.6 generated file
            FakeResult(existing_item),  # 2.1 tmdb_id check (finds existing)
            FakeResult(None),  # 2.2 TorBox item
            FakeResult(None),  # 2.3 TorBox file
            FakeResult(None),  # 2.4 library entry
            FakeResult(None),  # 2.5 generated file
            FakeResult(scalars=[]),  # generated cleanup query
            FakeResult(scalars=[]),  # TorBox files cleanup query
            FakeResult(scalars=[]),  # TorBox items cleanup query
        ]
    )

    repo = SyncStateRepository(cast(AsyncSession, session))
    _ = await repo.record_success(result, _resolved(tmp_path))

    # Should only have added 1 MediaItem (in iteration 1), none in iteration 2 since it reused existing_item
    media_items_added = [x for x in session.added if isinstance(x, MediaItem)]
    assert len(media_items_added) == 1
    assert media_items_added[0].title == "Title One"
    assert media_items_added[0].tmdb_id == "unique-tmdb-123"


@pytest.mark.asyncio
async def test_sync_state_repository_collapses_duplicates_by_missing_year(tmp_path: Path) -> None:
    file1 = tmp_path / "movies" / "Movie (2026)" / "Movie (2026).strm"
    file2 = tmp_path / "movies" / "Movie" / "Movie.strm"
    file1.parent.mkdir(parents=True, exist_ok=True)
    file2.parent.mkdir(parents=True, exist_ok=True)
    _ = file1.write_text("url1", encoding="utf-8")
    _ = file2.write_text("url2", encoding="utf-8")

    result = TorBoxStrmSyncResult(
        scanned_files=2,
        written_files=2,
        skipped_files=0,
        written_paths=(file1.resolve(strict=False), file2.resolve(strict=False)),
        synced_files=(
            SyncedStrmFile(
                path=file1.resolve(strict=False),
                entry_id="entry-1",
                category="movies",
                title="Movie",
                year=2026,
                season_number=None,
                episode_number=None,
                provider="torbox",
                provider_item_id="1",
                provider_file_id="2",
                content_hash="hash1",
                tmdb_id=None,
            ),
            SyncedStrmFile(
                path=file2.resolve(strict=False),
                entry_id="entry-2",
                category="movies",
                title="Movie",
                year=None,
                season_number=None,
                episode_number=None,
                provider="torbox",
                provider_item_id="1",
                provider_file_id="3",
                content_hash="hash2",
                tmdb_id=None,
            ),
        ),
    )

    existing_item = MediaItem(
        media_type="movies",
        title="Movie",
        year=2026,
        tmdb_id=None,
    )

    session = FakeSession(
        [
            FakeResult(None),  # 1.1 title+year check (returns None) -> creates item
            FakeResult(None),  # 1.2 TorBox item
            FakeResult(None),  # 1.3 TorBox file
            FakeResult(None),  # 1.4 library entry
            FakeResult(None),  # 1.5 generated file
            FakeResult(existing_item),  # 2.1 title+year check (matches year is None fallback)
            FakeResult(None),  # 2.2 TorBox item
            FakeResult(None),  # 2.3 TorBox file
            FakeResult(None),  # 2.4 library entry
            FakeResult(None),  # 2.5 generated file
            FakeResult(scalars=[]),  # generated cleanup query
            FakeResult(scalars=[]),  # TorBox files cleanup query
            FakeResult(scalars=[]),  # TorBox items cleanup query
        ]
    )

    repo = SyncStateRepository(cast(AsyncSession, session))
    _ = await repo.record_success(result, _resolved(tmp_path))

    media_items_added = [x for x in session.added if isinstance(x, MediaItem)]
    assert len(media_items_added) == 1
    assert media_items_added[0].title == "Movie"
    assert media_items_added[0].year == 2026


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
