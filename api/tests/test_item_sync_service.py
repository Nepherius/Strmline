from __future__ import annotations

from pathlib import Path
from typing import ClassVar, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.repositories.settings import SettingsSnapshot
from app.sync import item_service
from app.sync.item_service import TorBoxClientFactory, run_torbox_item_sync
from app.sync.torbox_strm import TorBoxStrmSyncResult


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeSettingsRepository:
    def __init__(self, session: object, settings: object) -> None:
        _ = (session, settings)

    async def snapshot_with_env(self) -> SettingsSnapshot:
        return SettingsSnapshot(
            base_url=None,
            library_root=FakeState.library_root,
            movies_enabled=True,
            shows_enabled=True,
            anime_enabled=True,
            playback_mode="direct",
            sync_interval_minutes=360,
            torbox_configured=True,
            tmdb_configured=False,
            resolver_configured=False,
            aiostreams_configured=True,
        )

    async def provider_api_key(self, provider: str) -> str | None:
        return "torbox-key" if provider == "torbox" else None


class FakeCoordinationRepository:
    released = False

    def __init__(self, session: object) -> None:
        _ = session

    async def try_lock(self) -> bool:
        return True

    async def release(self) -> None:
        type(self).released = True


class FakeSyncRunRepository:
    def __init__(self, session: object) -> None:
        _ = session

    async def record_success(self, result: object, **kwargs: object) -> int:
        FakeState.recorded_result = result
        FakeState.recorded_kwargs = kwargs
        return 91

    async def record_failure(self, **kwargs: object) -> int:
        FakeState.failure = kwargs
        return 92


class FakeSyncStateRepository:
    def __init__(self, session: object) -> None:
        _ = session

    async def persist_result(
        self,
        result: TorBoxStrmSyncResult,
        library_root: Path,
        **kwargs: object,
    ) -> None:
        FakeState.persisted_result = result
        FakeState.persisted_root = library_root
        FakeState.persisted_kwargs = kwargs


class FakeStreamSelectionRepository:
    def __init__(self, session: object) -> None:
        _ = session

    async def selected_for_torbox_item(self, torrent_id: str) -> tuple[object, ...]:
        FakeState.selected_torrent_id = torrent_id
        return ()


class FakeClassificationOverrideRepository:
    def __init__(self, session: object) -> None:
        _ = session

    async def list_all(self) -> tuple[object, ...]:
        return ()


class FakeLibraryExclusionRepository:
    def __init__(self, session: object) -> None:
        _ = session

    async def prefixes(self) -> tuple[str, ...]:
        return ()


class FakeSnapshot:
    @classmethod
    def create(cls, library_root: Path) -> FakeSnapshot:
        FakeState.snapshot_root = library_root
        return cls()

    def restore(self) -> None:
        FakeState.restored = True


class FakeClient:
    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        _ = args

    async def get_download(self, kind: str, item_id: str) -> dict[str, object] | None:
        FakeState.download_request = (kind, item_id)
        return {
            "id": 777,
            "hash": "ab" * 20,
            "name": "Test.Movie.2026",
            "files": [],
        }


class FakeTorBoxStrmSync:
    def __init__(self, **kwargs: object) -> None:
        FakeState.generator_kwargs = kwargs

    async def run(
        self,
        kinds: tuple[str, ...],
        *,
        partial: bool,
    ) -> TorBoxStrmSyncResult:
        FakeState.run_kinds = kinds
        FakeState.run_partial = partial
        return TorBoxStrmSyncResult(
            scanned_files=1,
            written_files=1,
            skipped_files=0,
            written_paths=(),
            synced_files=(),
            partial=partial,
        )


class FakeState:
    library_root: ClassVar[str] = ""
    recorded_result: ClassVar[object | None] = None
    recorded_kwargs: ClassVar[dict[str, object]] = {}
    failure: ClassVar[dict[str, object] | None] = None
    persisted_result: ClassVar[TorBoxStrmSyncResult | None] = None
    persisted_root: ClassVar[Path | None] = None
    persisted_kwargs: ClassVar[dict[str, object]] = {}
    selected_torrent_id: ClassVar[str | None] = None
    snapshot_root: ClassVar[Path | None] = None
    restored: ClassVar[bool] = False
    download_request: ClassVar[tuple[str, str] | None] = None
    generator_kwargs: ClassVar[dict[str, object]] = {}
    run_kinds: ClassVar[tuple[str, ...]] = ()
    run_partial: ClassVar[bool] = False


@pytest.mark.asyncio
async def test_item_sync_only_persists_partial_target_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeState.library_root = str(tmp_path)
    FakeState.persisted_result = None
    FakeState.restored = False
    FakeCoordinationRepository.released = False
    monkeypatch.setattr(item_service, "AppSettingsRepository", FakeSettingsRepository)
    monkeypatch.setattr(item_service, "SyncCoordinationRepository", FakeCoordinationRepository)
    monkeypatch.setattr(item_service, "SyncRunRepository", FakeSyncRunRepository)
    monkeypatch.setattr(item_service, "SyncLibraryStateRepository", FakeSyncStateRepository)
    monkeypatch.setattr(item_service, "StreamSelectionRepository", FakeStreamSelectionRepository)
    monkeypatch.setattr(
        item_service,
        "ClassificationOverrideRepository",
        FakeClassificationOverrideRepository,
    )
    monkeypatch.setattr(
        item_service,
        "LibraryExclusionRepository",
        FakeLibraryExclusionRepository,
    )
    monkeypatch.setattr(item_service, "LibraryMutationJournal", FakeSnapshot)
    monkeypatch.setattr(item_service, "TorBoxStrmSync", FakeTorBoxStrmSync)

    async def fake_selected_identities(
        *args: object,
    ) -> tuple[dict[str, object], dict[str, object]]:
        _ = args
        return {}, {}

    async def fake_cache_posters(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)

    monkeypatch.setattr(item_service, "selected_media_identities", fake_selected_identities)
    monkeypatch.setattr(item_service, "_cache_item_posters", fake_cache_posters)

    def client_factory(**kwargs: object) -> FakeClient:
        _ = kwargs
        return FakeClient()

    session = FakeSession()
    summary = await run_torbox_item_sync(
        cast(AsyncSession, session),
        Settings(),
        torrent_id="777",
        client_factory=cast(TorBoxClientFactory, client_factory),
    )

    assert summary.sync_run_id == 91
    assert FakeState.download_request == ("torrents", "777")
    assert FakeState.selected_torrent_id == "777"
    assert FakeState.run_kinds == ("torrents",)
    assert FakeState.run_partial is True
    assert FakeState.persisted_result is not None
    assert FakeState.persisted_result.partial is True
    assert FakeState.persisted_kwargs == {}
    assert FakeState.persisted_root == tmp_path
    assert FakeState.restored is False
    assert FakeCoordinationRepository.released is True
