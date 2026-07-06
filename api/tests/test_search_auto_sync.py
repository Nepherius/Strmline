from __future__ import annotations

from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.search import auto_sync
from app.search.auto_sync import auto_sync_after_stream_add
from app.sync.service import SyncAlreadyRunningError, SyncConfigurationError, SyncRunSummary


@pytest.mark.asyncio
async def test_auto_sync_reports_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run_sync(*args: object, **kwargs: object) -> SyncRunSummary:
        _ = (args, kwargs)
        return SyncRunSummary(
            sync_run_id=44,
            playback_mode="resolver",
            library_root="/library",
            scanned_files=3,
            written_files=2,
            skipped_files=1,
        )

    monkeypatch.setattr(auto_sync, "run_torbox_account_sync", fake_run_sync)

    outcome = await auto_sync_after_stream_add(
        session=cast(AsyncSession, object()),
        settings=cast(Settings, object()),
        action_message="Added.",
    )

    assert outcome.status == "success"
    assert outcome.sync_run_id == 44
    assert outcome.message == "Added. Synced library: 2 written, 1 skipped."


@pytest.mark.asyncio
async def test_auto_sync_reports_already_running(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run_sync(*args: object, **kwargs: object) -> SyncRunSummary:
        _ = (args, kwargs)
        raise SyncAlreadyRunningError("A sync run is already in progress.")

    monkeypatch.setattr(auto_sync, "run_torbox_account_sync", fake_run_sync)

    outcome = await auto_sync_after_stream_add(
        session=cast(AsyncSession, object()),
        settings=cast(Settings, object()),
        action_message="Added.",
    )

    assert outcome.status == "already_running"
    assert outcome.sync_run_id is None
    assert outcome.message == "Added. Sync is already running."


@pytest.mark.asyncio
async def test_auto_sync_reports_configuration_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run_sync(*args: object, **kwargs: object) -> SyncRunSummary:
        _ = (args, kwargs)
        raise SyncConfigurationError("Library root is not configured.")

    monkeypatch.setattr(auto_sync, "run_torbox_account_sync", fake_run_sync)

    outcome = await auto_sync_after_stream_add(
        session=cast(AsyncSession, object()),
        settings=cast(Settings, object()),
        action_message="Added.",
    )

    assert outcome.status == "failed"
    assert outcome.sync_run_id is None
    assert outcome.message == "Added. Automatic sync failed: Library root is not configured."
