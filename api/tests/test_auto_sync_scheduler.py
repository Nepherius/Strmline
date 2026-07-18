from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import Settings
from app.db.repositories.settings import SettingsSnapshot
from app.sync import scheduler as scheduler_module
from app.sync.scheduler import (
    AUTO_SYNC_JOB_ID,
    SEASON_COMPLETION_JOB_ID,
    AsyncSessionFactory,
    AutoSyncScheduler,
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


class FakeScheduler:
    def __init__(self) -> None:
        self.running = False
        self.jobs: dict[str, dict[str, object]] = {}
        self.removed: list[str] = []

    def start(self) -> None:
        self.running = True

    def shutdown(self, *, wait: bool = True) -> None:
        _ = wait
        self.running = False

    def add_job(
        self,
        job: Callable[[], Awaitable[None]],
        *,
        trigger: IntervalTrigger,
        next_run_time: datetime,
        **options: object,
    ) -> object:
        job_id = options["id"]
        assert isinstance(job_id, str)
        self.jobs[job_id] = {
            "job": job,
            "trigger": trigger,
            "next_run_time": next_run_time,
            **options,
        }
        return object()

    def get_job(self, job_id: str) -> object | None:
        return self.jobs.get(job_id)

    def remove_job(self, job_id: str) -> None:
        self.removed.append(job_id)
        _ = self.jobs.pop(job_id, None)


@pytest.mark.asyncio
async def test_auto_sync_scheduler_uses_saved_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler = FakeScheduler()
    snapshot = _settings_snapshot(sync_interval_minutes=5, torbox_configured=True)
    monkeypatch.setattr(scheduler_module, "AppSettingsRepository", _repository(snapshot))

    auto_sync = AutoSyncScheduler(
        session_factory=cast(AsyncSessionFactory, FakeSessionFactory()),
        scheduler=cast(AsyncIOScheduler, scheduler),
        settings_provider=Settings,
    )

    await auto_sync.start()

    job = scheduler.jobs[AUTO_SYNC_JOB_ID]
    assert scheduler.running is True
    trigger = job["trigger"]
    assert isinstance(trigger, IntervalTrigger)
    assert trigger.interval == timedelta(minutes=5)  # pyright: ignore[reportUnknownMemberType]
    assert isinstance(job["next_run_time"], datetime)


@pytest.mark.asyncio
async def test_auto_sync_scheduler_removes_job_without_torbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler = FakeScheduler()
    scheduler.jobs[AUTO_SYNC_JOB_ID] = {"args": (), "kwargs": {}}
    snapshot = _settings_snapshot(torbox_configured=False)
    monkeypatch.setattr(scheduler_module, "AppSettingsRepository", _repository(snapshot))

    auto_sync = AutoSyncScheduler(
        session_factory=cast(AsyncSessionFactory, FakeSessionFactory()),
        scheduler=cast(AsyncIOScheduler, scheduler),
        settings_provider=Settings,
    )

    await auto_sync.reschedule_from_settings()

    assert AUTO_SYNC_JOB_ID not in scheduler.jobs
    assert scheduler.removed == [AUTO_SYNC_JOB_ID]


@pytest.mark.asyncio
async def test_auto_sync_scheduler_runs_sync_with_auto_source() -> None:
    captured_kwargs: dict[str, object] = {}

    async def fake_sync_runner(*args: object, **kwargs: object) -> object:
        _ = args
        captured_kwargs.update(kwargs)
        return object()

    auto_sync = AutoSyncScheduler(
        session_factory=cast(AsyncSessionFactory, FakeSessionFactory()),
        scheduler=cast(AsyncIOScheduler, FakeScheduler()),
        settings_provider=Settings,
        sync_runner=cast(SyncRunner, fake_sync_runner),
    )

    await auto_sync.run_once()

    assert captured_kwargs["source"] == "auto"


@pytest.mark.asyncio
async def test_season_completion_runs_immediately_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = FakeScheduler()
    snapshot = _settings_snapshot(
        season_auto_complete_enabled=True,
        season_auto_complete_interval_days=3,
    )
    monkeypatch.setattr(scheduler_module, "AppSettingsRepository", _repository(snapshot))
    before = datetime.now(UTC)

    scheduler = AutoSyncScheduler(
        session_factory=cast(AsyncSessionFactory, FakeSessionFactory()),
        scheduler=cast(AsyncIOScheduler, backend),
        settings_provider=Settings,
    )
    await scheduler.start()

    job = backend.jobs[SEASON_COMPLETION_JOB_ID]
    trigger = job["trigger"]
    assert isinstance(trigger, IntervalTrigger)
    assert trigger.interval == timedelta(days=3)  # pyright: ignore[reportUnknownMemberType]
    next_run_time = job["next_run_time"]
    assert isinstance(next_run_time, datetime)
    assert next_run_time >= before
    assert next_run_time <= before + timedelta(seconds=1)


@pytest.mark.asyncio
async def test_season_completion_remains_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = FakeScheduler()
    monkeypatch.setattr(
        scheduler_module,
        "AppSettingsRepository",
        _repository(_settings_snapshot()),
    )
    scheduler = AutoSyncScheduler(
        session_factory=cast(AsyncSessionFactory, FakeSessionFactory()),
        scheduler=cast(AsyncIOScheduler, backend),
        settings_provider=Settings,
    )

    await scheduler.start()

    assert SEASON_COMPLETION_JOB_ID not in backend.jobs


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
