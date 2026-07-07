from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import datetime
from typing import cast

import pytest

from app.core.config import Settings
from app.db.repositories.settings import SettingsSnapshot
from app.sync import scheduler as scheduler_module
from app.sync.scheduler import (
    AUTO_SYNC_JOB_ID,
    AsyncSessionFactory,
    AutoSyncScheduler,
    SchedulerBackend,
    SyncRunner,
)


class FakeSessionContext:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *args: object) -> None:
        _ = args


class FakeSessionFactory:
    def __call__(self) -> FakeSessionContext:
        return FakeSessionContext()


class FakeSchedulerBackend:
    def __init__(self) -> None:
        self.running = False
        self.jobs: dict[str, dict[str, object]] = {}
        self.removed: list[str] = []

    def start(self) -> None:
        self.running = True

    def shutdown(self) -> None:
        self.running = False

    def schedule_auto_sync(
        self,
        job: Callable[[], Awaitable[None]],
        *,
        interval_minutes: int,
        next_run_time: datetime,
    ) -> None:
        self.jobs[AUTO_SYNC_JOB_ID] = {
            "job": job,
            "interval_minutes": interval_minutes,
            "next_run_time": next_run_time,
        }

    def remove_auto_sync(self) -> None:
        self.removed.append(AUTO_SYNC_JOB_ID)
        _ = self.jobs.pop(AUTO_SYNC_JOB_ID, None)


@pytest.mark.asyncio
async def test_auto_sync_scheduler_uses_saved_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = FakeSchedulerBackend()
    snapshot = _settings_snapshot(sync_interval_minutes=5, torbox_configured=True)
    monkeypatch.setattr(scheduler_module, "AppSettingsRepository", _repository(snapshot))

    auto_sync = AutoSyncScheduler(
        session_factory=cast(AsyncSessionFactory, FakeSessionFactory()),
        backend=cast(SchedulerBackend, backend),
        settings_provider=Settings,
    )

    await auto_sync.start()

    job = backend.jobs[AUTO_SYNC_JOB_ID]
    assert backend.running is True
    assert job["interval_minutes"] == 5
    assert isinstance(job["next_run_time"], datetime)


@pytest.mark.asyncio
async def test_auto_sync_scheduler_removes_job_without_torbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = FakeSchedulerBackend()
    backend.jobs[AUTO_SYNC_JOB_ID] = {"args": (), "kwargs": {}}
    snapshot = _settings_snapshot(torbox_configured=False)
    monkeypatch.setattr(scheduler_module, "AppSettingsRepository", _repository(snapshot))

    auto_sync = AutoSyncScheduler(
        session_factory=cast(AsyncSessionFactory, FakeSessionFactory()),
        backend=cast(SchedulerBackend, backend),
        settings_provider=Settings,
    )

    await auto_sync.reschedule_from_settings()

    assert AUTO_SYNC_JOB_ID not in backend.jobs
    assert backend.removed == [AUTO_SYNC_JOB_ID]


@pytest.mark.asyncio
async def test_auto_sync_scheduler_runs_sync_with_auto_source() -> None:
    captured_kwargs: dict[str, object] = {}

    async def fake_sync_runner(*args: object, **kwargs: object) -> object:
        _ = args
        captured_kwargs.update(kwargs)
        return object()

    auto_sync = AutoSyncScheduler(
        session_factory=cast(AsyncSessionFactory, FakeSessionFactory()),
        backend=cast(SchedulerBackend, FakeSchedulerBackend()),
        settings_provider=Settings,
        sync_runner=cast(SyncRunner, fake_sync_runner),
    )

    await auto_sync.run_once()

    assert captured_kwargs["source"] == "auto"


def _settings_snapshot(**changes: object) -> SettingsSnapshot:
    snapshot = SettingsSnapshot(
        base_url="http://127.0.0.1:8001",
        library_root="/library",
        movies_enabled=True,
        shows_enabled=True,
        anime_enabled=True,
        playback_mode="resolver",
        sync_interval_minutes=360,
        torbox_configured=True,
        tmdb_configured=False,
        resolver_configured=True,
        aiostreams_configured=False,
    )
    return replace(snapshot, **changes)


def _repository(snapshot: SettingsSnapshot) -> type:
    class FakeSettingsRepository:
        def __init__(self, session: object, settings: object) -> None:
            _ = (session, settings)

        async def snapshot_with_env(self) -> SettingsSnapshot:
            return snapshot

    return FakeSettingsRepository
