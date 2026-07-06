from pathlib import Path
from typing import cast, override

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.repositories.settings import SettingsSnapshot
from app.providers.torbox.client import TorBoxAPIError
from app.sync import service as sync_service
from app.sync.service import SyncExecutionError, run_torbox_account_sync
from app.sync.torbox_strm import ResolverUrlConfig, TorBoxStrmSyncResult


class FakeSyncStateRepository:
    def __init__(self, session: object) -> None:
        _ = session

    async def record_success(self, result: object, library_root: object, **kwargs: object) -> int:
        _ = result
        _ = library_root
        _ = kwargs
        return 12

    async def record_failure(self, **kwargs: object) -> int:
        _ = kwargs
        return 13


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


@pytest.mark.asyncio
async def test_sync_service_uses_saved_resolver_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def fake_client_factory(**kwargs: object) -> FakeClient:
        _ = kwargs
        return FakeClient()

    monkeypatch.setattr(sync_service, "AppSettingsRepository", fake_settings_repository(tmp_path))
    monkeypatch.setattr(sync_service, "LibraryExclusionRepository", FakeLibraryExclusionRepository)
    monkeypatch.setattr(sync_service, "SyncStateRepository", FakeSyncStateRepository)
    monkeypatch.setattr(sync_service, "TorBoxStrmSync", fake_torbox_strm_sync(captured))
    monkeypatch.setattr(sync_service, "ensure_selected_streams_in_torbox", no_selected_streams)

    summary = await run_torbox_account_sync(
        cast(AsyncSession, object()),
        Settings(),
        client_factory=cast(sync_service.TorBoxClientFactory, fake_client_factory),
    )

    resolver = captured["resolver"]
    assert isinstance(resolver, ResolverUrlConfig)
    assert resolver.token == "saved-resolver-token"  # noqa: S105
    assert captured["anime_classifier"] is not None
    assert captured["excluded_prefixes"] == ("shows/Removed Show",)
    assert summary.sync_run_id == 12


@pytest.mark.asyncio
async def test_sync_service_records_provider_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    failures: list[dict[str, object]] = []

    def fake_client_factory(**kwargs: object) -> FakeClient:
        _ = kwargs
        return FakeClient()

    class CapturingSyncStateRepository(FakeSyncStateRepository):
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
    monkeypatch.setattr(sync_service, "LibraryExclusionRepository", FakeLibraryExclusionRepository)
    monkeypatch.setattr(sync_service, "SyncStateRepository", CapturingSyncStateRepository)
    monkeypatch.setattr(sync_service, "TorBoxStrmSync", FailingTorBoxStrmSync)
    monkeypatch.setattr(sync_service, "ensure_selected_streams_in_torbox", no_selected_streams)

    with pytest.raises(SyncExecutionError):
        _ = await run_torbox_account_sync(
            cast(AsyncSession, object()),
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
