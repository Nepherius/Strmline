from pathlib import Path
from types import SimpleNamespace
from typing import cast, override

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.repositories.media_identity import (
    AliasIdentityBinding,
    PersistedMediaIdentity,
    SourceIdentityBinding,
)
from app.db.repositories.settings import SettingsSnapshot
from app.db.repositories.stream_selection import StreamSelectionRecord
from app.domain.media_identity import IdentityAuthority
from app.providers.torbox.client import TorBoxAPIError
from app.sync import identity_inputs as sync_identity_inputs, service as sync_service
from app.sync.media_identity import MediaIdentity
from app.sync.service import SyncExecutionError, run_torbox_account_sync
from app.sync.torbox_strm import ResolverUrlConfig, TorBoxStrmSyncResult


class FakeSyncLibraryStateRepository:
    def __init__(self, session: object) -> None:
        _ = session

    async def persist_result(self, result: object, library_root: object, **kwargs: object) -> None:
        _ = result
        _ = library_root
        _ = kwargs

    async def retained_library_paths(
        self,
        library_root: Path,
        info_hashes: frozenset[str],
    ) -> set[Path]:
        _ = library_root
        _ = info_hashes
        return set()


class FakeSyncRunRepository:
    def __init__(self, session: object) -> None:
        _ = session

    async def record_success(self, result: object, **kwargs: object) -> int:
        _ = (result, kwargs)
        return 12

    async def record_failure(self, **kwargs: object) -> int:
        _ = kwargs
        return 13


class FakeSession:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        pass


class FakeStreamSelectionRepository:
    def __init__(self, session: object) -> None:
        _ = session

    async def list_selected(self) -> tuple[object, ...]:
        return ()


class FakeClient:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *args: object) -> None:
        _ = args


class FakeLibraryExclusionRepository:
    def __init__(self, session: object) -> None:
        _ = session

    async def prefixes(self) -> tuple[str, ...]:
        return ("shows/Removed Show",)


class FakeClassificationOverrideRepository:
    def __init__(self, session: object) -> None:
        _ = session

    async def list_all(self) -> tuple[object, ...]:
        return ()


class FakeMediaIdentityRepository:
    def __init__(self, session: object) -> None:
        _ = session

    async def source_bindings(self) -> tuple[SourceIdentityBinding, ...]:
        return ()

    async def alias_bindings(self) -> tuple[AliasIdentityBinding, ...]:
        return ()


class FakeSyncCoordinationRepository:
    def __init__(self, session: object) -> None:
        _ = session

    async def try_lock(self) -> bool:
        return True

    async def release(self) -> None:
        pass


@pytest.mark.asyncio
async def test_sync_service_uses_saved_resolver_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    retained_hash_requests: list[frozenset[str]] = []

    class CapturingLibraryStateRepository(FakeSyncLibraryStateRepository):
        @override
        async def retained_library_paths(
            self,
            library_root: Path,
            info_hashes: frozenset[str],
        ) -> set[Path]:
            _ = library_root
            retained_hash_requests.append(info_hashes)
            return set()

    def fake_client_factory(**kwargs: object) -> FakeClient:
        _ = kwargs
        return FakeClient()

    monkeypatch.setattr(sync_service, "AppSettingsRepository", fake_settings_repository(tmp_path))
    monkeypatch.setattr(
        sync_service,
        "ClassificationOverrideRepository",
        FakeClassificationOverrideRepository,
    )
    monkeypatch.setattr(sync_service, "LibraryExclusionRepository", FakeLibraryExclusionRepository)
    monkeypatch.setattr(
        sync_identity_inputs,
        "MediaIdentityRepository",
        FakeMediaIdentityRepository,
    )
    monkeypatch.setattr(
        sync_service,
        "SyncCoordinationRepository",
        FakeSyncCoordinationRepository,
    )
    monkeypatch.setattr(
        sync_service,
        "SyncLibraryStateRepository",
        CapturingLibraryStateRepository,
    )
    monkeypatch.setattr(sync_service, "SyncRunRepository", FakeSyncRunRepository)
    monkeypatch.setattr(
        sync_service,
        "StreamSelectionRepository",
        FakeStreamSelectionRepository,
    )
    monkeypatch.setattr(sync_service, "TorBoxStrmSync", fake_torbox_strm_sync(captured))
    monkeypatch.setattr(sync_service, "ensure_selected_streams_in_torbox", no_selected_streams)

    session = FakeSession()
    summary = await run_torbox_account_sync(
        cast(AsyncSession, session),
        Settings(),
        client_factory=cast(sync_service.TorBoxClientFactory, fake_client_factory),
    )

    resolver = captured["resolver"]
    assert isinstance(resolver, ResolverUrlConfig)
    assert resolver.token == "saved-resolver-token"  # noqa: S105
    assert captured["anime_classifier"] is not None
    assert captured["classification_overrides"] == ()
    assert captured["excluded_prefixes"] == ("shows/Removed Show",)
    assert retained_hash_requests == [frozenset()]
    assert summary.sync_run_id == 12
    assert session.committed is True


@pytest.mark.asyncio
async def test_sync_service_records_provider_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    failures: list[dict[str, object]] = []

    def fake_client_factory(**kwargs: object) -> FakeClient:
        _ = kwargs
        return FakeClient()

    class CapturingSyncRunRepository(FakeSyncRunRepository):
        @override
        async def record_failure(self, **kwargs: object) -> int:
            failures.append(kwargs)
            return 13

    class FailingTorBoxStrmSync:
        def __init__(self, **kwargs: object) -> None:
            _ = kwargs

        async def run(self) -> TorBoxStrmSyncResult:
            raise TorBoxAPIError("TorBox request failed with status 503.")

    monkeypatch.setattr(sync_service, "AppSettingsRepository", fake_settings_repository(tmp_path))
    monkeypatch.setattr(
        sync_service,
        "ClassificationOverrideRepository",
        FakeClassificationOverrideRepository,
    )
    monkeypatch.setattr(sync_service, "LibraryExclusionRepository", FakeLibraryExclusionRepository)
    monkeypatch.setattr(
        sync_identity_inputs,
        "MediaIdentityRepository",
        FakeMediaIdentityRepository,
    )
    monkeypatch.setattr(
        sync_service,
        "SyncCoordinationRepository",
        FakeSyncCoordinationRepository,
    )
    monkeypatch.setattr(
        sync_service,
        "SyncLibraryStateRepository",
        FakeSyncLibraryStateRepository,
    )
    monkeypatch.setattr(sync_service, "SyncRunRepository", CapturingSyncRunRepository)
    monkeypatch.setattr(
        sync_service,
        "StreamSelectionRepository",
        FakeStreamSelectionRepository,
    )
    monkeypatch.setattr(sync_service, "TorBoxStrmSync", FailingTorBoxStrmSync)
    monkeypatch.setattr(sync_service, "ensure_selected_streams_in_torbox", no_selected_streams)

    session = FakeSession()
    with pytest.raises(SyncExecutionError):
        _ = await run_torbox_account_sync(
            cast(AsyncSession, session),
            Settings(),
            client_factory=cast(sync_service.TorBoxClientFactory, fake_client_factory),
        )

    assert failures == [
        {
            "phase": "torbox_sync",
            "message": "TorBox request failed with status 503.",
            "source": "manual",
        }
    ]
    assert session.committed is True


@pytest.mark.asyncio
async def test_sync_service_restores_files_when_database_persistence_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    existing = tmp_path / "shows" / "Show" / "Show - S01E01.strm"
    existing.parent.mkdir(parents=True)
    _ = existing.write_text("original\n", encoding="utf-8")
    failures: list[dict[str, object]] = []

    class FailingLibraryStateRepository(FakeSyncLibraryStateRepository):
        @override
        async def persist_result(
            self,
            result: object,
            library_root: object,
            **kwargs: object,
        ) -> None:
            _ = (result, library_root, kwargs)
            raise RuntimeError("database unavailable")

    class CapturingRunRepository(FakeSyncRunRepository):
        @override
        async def record_failure(self, **kwargs: object) -> int:
            failures.append(kwargs)
            return 13

    class WritingTorBoxStrmSync:
        def __init__(self, **kwargs: object) -> None:
            self.library_root = cast(Path, kwargs["library_root"])

        async def run(self) -> TorBoxStrmSyncResult:
            changed = self.library_root / "shows" / "Show" / "Show - S01E01.strm"
            new_file = self.library_root / "shows" / "Show" / "Show - S01E02.strm"
            _ = changed.write_text("changed\n", encoding="utf-8")
            _ = new_file.write_text("new\n", encoding="utf-8")
            return TorBoxStrmSyncResult(2, 2, 0, (changed, new_file), ())

    def fake_client_factory(**kwargs: object) -> FakeClient:
        _ = kwargs
        return FakeClient()

    monkeypatch.setattr(sync_service, "AppSettingsRepository", fake_settings_repository(tmp_path))
    monkeypatch.setattr(
        sync_service,
        "ClassificationOverrideRepository",
        FakeClassificationOverrideRepository,
    )
    monkeypatch.setattr(sync_service, "LibraryExclusionRepository", FakeLibraryExclusionRepository)
    monkeypatch.setattr(
        sync_identity_inputs,
        "MediaIdentityRepository",
        FakeMediaIdentityRepository,
    )
    monkeypatch.setattr(sync_service, "SyncCoordinationRepository", FakeSyncCoordinationRepository)
    monkeypatch.setattr(
        sync_service,
        "SyncLibraryStateRepository",
        FailingLibraryStateRepository,
    )
    monkeypatch.setattr(sync_service, "SyncRunRepository", CapturingRunRepository)
    monkeypatch.setattr(sync_service, "StreamSelectionRepository", FakeStreamSelectionRepository)
    monkeypatch.setattr(sync_service, "TorBoxStrmSync", WritingTorBoxStrmSync)
    monkeypatch.setattr(sync_service, "ensure_selected_streams_in_torbox", no_selected_streams)

    with pytest.raises(SyncExecutionError, match="generated files were restored"):
        _ = await run_torbox_account_sync(
            cast(AsyncSession, FakeSession()),
            Settings(),
            client_factory=cast(sync_service.TorBoxClientFactory, fake_client_factory),
        )

    assert existing.read_text(encoding="utf-8") == "original\n"
    assert (tmp_path / "shows" / "Show" / "Show - S01E02.strm").exists() is False
    assert failures == [
        {
            "phase": "persistence",
            "message": "Database persistence failed; generated files were restored.",
            "source": "manual",
            "scanned_count": 2,
            "written_count": 2,
            "skipped_count": 0,
        }
    ]


def fake_settings_repository(library_root: Path) -> type:
    class FakeSettingsRepository:
        def __init__(self, session: object, settings: object) -> None:
            _ = session
            _ = settings

        async def snapshot_with_env(self) -> SettingsSnapshot:
            return SettingsSnapshot(
                base_url="http://127.0.0.1:8001",
                library_root=str(library_root),
                movies_enabled=True,
                shows_enabled=True,
                anime_enabled=True,
                playback_mode="resolver",
                sync_interval_minutes=360,
                torbox_configured=True,
                tmdb_configured=True,
                resolver_configured=True,
                aiostreams_configured=False,
            )

        async def provider_api_key(self, provider: object) -> str:
            _ = provider
            return "torbox-secret"

        async def resolver_token_value(self) -> str:
            return "saved-resolver-token"

        async def aiostreams_base_url_value(self) -> str | None:
            return None

    return FakeSettingsRepository


async def no_selected_streams(**kwargs: object) -> None:
    _ = kwargs


@pytest.mark.asyncio
async def test_selected_media_identities_backfill_legacy_stream_selections() -> None:
    selections = tuple(
        StreamSelectionRecord(
            stream_key=f"stream-{index}",
            media_type="series",
            media_id=f"tt21975436:{season}:1",
            title="Release title",
            source_name=None,
            info_hash=f"HASH-{index}",
            torbox_torrent_id=str(index),
            status="selected",
        )
        for index, season in ((8, 1), (9, 2))
    )

    class CapturingRepository:
        def __init__(self) -> None:
            self.updates: list[tuple[str, dict[str, object]]] = []

        async def update_media_identity(self, stream_key: str, **kwargs: object) -> None:
            self.updates.append((stream_key, kwargs))

    class ExternalIdentityResolver:
        def __init__(self) -> None:
            self.calls = 0
            self.external_ids: list[str] = []

        async def resolve_external_id(self, external_id: str, media_type: str) -> MediaIdentity:
            _ = media_type
            self.calls += 1
            self.external_ids.append(external_id)
            return MediaIdentity(
                tmdb_id="207468",
                title="Kaiju No. 8",
                year=2024,
                media_type="tv",
                poster_path="/kaiju.jpg",
            )

    repository = CapturingRepository()
    resolver = ExternalIdentityResolver()

    by_torrent_id, by_info_hash = await sync_identity_inputs.selected_media_identities(
        cast(sync_service.StreamSelectionRepository, repository),
        selections,
        cast(sync_service.MediaIdentityResolver, resolver),
    )

    assert resolver.calls == 1
    assert resolver.external_ids == ["tt21975436"]
    assert set(by_torrent_id) == {"8", "9"}
    assert set(by_info_hash) == {"hash-8", "hash-9"}
    assert {identity.title for identity in by_torrent_id.values()} == {"Kaiju No. 8"}
    assert [stream_key for stream_key, _ in repository.updates] == ["stream-8", "stream-9"]


def test_watchlist_identities_include_movies_shows_and_anime() -> None:
    result = SimpleNamespace(
        synced_files=(
            SimpleNamespace(category="movies", tmdb_id="10"),
            SimpleNamespace(category="shows", tmdb_id="20"),
            SimpleNamespace(category="anime", tmdb_id="30"),
            SimpleNamespace(category="shows", tmdb_id=None),
        )
    )

    assert sync_service._watchlist_identities(  # pyright: ignore[reportPrivateUsage]
        cast(TorBoxStrmSyncResult, result)
    ) == {("movie", 10), ("series", 20), ("series", 30)}


def test_manual_source_binding_overrides_stale_stream_selection_identity() -> None:
    stale_identity = MediaIdentity(
        tmdb_id="99999",
        title="Wrong Bookworm Match",
        year=2022,
        media_type="tv",
    )
    by_torrent_id = {"44": stale_identity}
    by_info_hash = {"abc123": stale_identity}
    persisted = (
        SourceIdentityBinding(
            source_kind="torrents",
            source_item_id="44",
            info_hash="ABC123",
            identity=PersistedMediaIdentity(
                media_item_id=1,
                content_kind="series",
                tmdb_id="91768",
                title="Ascendance of a Bookworm",
                year=2019,
                provider_media_kind="tv",
                authority=IdentityAuthority.MANUAL.value,
                authoritative=True,
                confidence=100,
                resolver_version=None,
            ),
        ),
    )

    sync_identity_inputs.merge_source_bindings(
        by_torrent_id,
        by_info_hash,
        persisted,
    )

    assert by_torrent_id["44"].tmdb_id == "91768"
    assert by_info_hash["abc123"].tmdb_id == "91768"


def test_provider_binding_does_not_override_search_confirmed_identity() -> None:
    selected_identity = MediaIdentity(
        tmdb_id="91768",
        title="Ascendance of a Bookworm",
        year=2019,
        media_type="tv",
        authority=IdentityAuthority.SEARCH_CONFIRMED,
    )
    by_torrent_id = {"44": selected_identity}
    by_info_hash: dict[str, MediaIdentity] = {}
    persisted = (
        SourceIdentityBinding(
            source_kind="torrents",
            source_item_id="44",
            info_hash="ABC123",
            identity=PersistedMediaIdentity(
                media_item_id=2,
                content_kind="series",
                tmdb_id="99999",
                title="Old Match",
                year=2022,
                provider_media_kind="tv",
                authority=IdentityAuthority.PROVIDER_RESOLVED.value,
                authoritative=False,
                confidence=70,
                resolver_version="tmdb-v2",
            ),
        ),
    )

    sync_identity_inputs.merge_source_bindings(
        by_torrent_id,
        by_info_hash,
        persisted,
    )

    assert by_torrent_id["44"] is selected_identity
    assert by_info_hash == {"abc123": selected_identity}


def test_stale_files_are_removed_only_by_post_commit_reconciliation(tmp_path: Path) -> None:
    current = tmp_path / "anime" / "Kaiju No. 8" / "Season 01" / "S01E01.strm"
    stale = tmp_path / "anime" / "Kaijuu 8-gou" / "Season 01" / "S01E01.strm"
    preserved = tmp_path / "movies" / "Saved Movie" / "Saved Movie.strm"
    for path in (current, stale, preserved):
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text("stream\n", encoding="utf-8")
    result = TorBoxStrmSyncResult(
        scanned_files=1,
        written_files=1,
        skipped_files=0,
        written_paths=(current,),
        synced_files=(),
    )

    sync_service._remove_stale_sync_files(  # pyright: ignore[reportPrivateUsage]
        tmp_path,
        result,
        {preserved},
    )

    assert current.exists() is True
    assert preserved.exists() is True
    assert stale.exists() is False


def test_only_selected_hashes_absent_from_current_sync_are_retained() -> None:
    result = SimpleNamespace(
        synced_files=(
            SimpleNamespace(info_hash="current-hash"),
            SimpleNamespace(info_hash=None),
        )
    )

    retained = sync_service._absent_selected_hashes(  # pyright: ignore[reportPrivateUsage]
        frozenset({"current-hash", "temporarily-absent-hash"}),
        cast(TorBoxStrmSyncResult, result),
    )

    assert retained == frozenset({"temporarily-absent-hash"})


def fake_torbox_strm_sync(captured: dict[str, object]) -> type:
    class FakeTorBoxStrmSync:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        async def run(self) -> TorBoxStrmSyncResult:
            return TorBoxStrmSyncResult(
                scanned_files=0,
                written_files=0,
                skipped_files=0,
                written_paths=(),
                synced_files=(),
            )

    return FakeTorBoxStrmSync
