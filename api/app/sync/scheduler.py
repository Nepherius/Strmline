from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from operator import attrgetter
from typing import Protocol, cast

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.dependencies import get_session_factory
from app.db.repositories.settings import AppSettingsRepository, SettingsSnapshot
from app.season_completion.service import (
    SeasonCompletionAlreadyRunningError,
    run_season_completion,
)
from app.sync.service import (
    SyncAlreadyRunningError,
    SyncConfigurationError,
    SyncExecutionError,
    run_torbox_account_sync,
)

AUTO_SYNC_JOB_ID = "torbox-auto-sync"
SEASON_COMPLETION_JOB_ID = "season-auto-complete"

logger = logging.getLogger(__name__)


class SchedulerBackend(Protocol):
    running: bool

    def start(self) -> None: ...

    def shutdown(self) -> None: ...

    def schedule_auto_sync(
        self,
        job: Callable[[], Awaitable[None]],
        *,
        interval_minutes: int,
        next_run_time: datetime,
    ) -> None: ...

    def remove_auto_sync(self) -> None: ...

    def schedule_season_completion(
        self,
        job: Callable[[], Awaitable[None]],
        *,
        interval_days: int,
        next_run_time: datetime,
    ) -> None: ...

    def remove_season_completion(self) -> None: ...


SyncRunner = Callable[..., Awaitable[object]]
SeasonCompletionRunner = Callable[..., Awaitable[object]]
AsyncSessionFactory = Callable[[], AsyncSession]


class ApschedulerBackend:
    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler(timezone=UTC)

    @property
    def running(self) -> bool:
        return self._scheduler.running

    def start(self) -> None:
        self._scheduler.start()

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)

    def schedule_auto_sync(
        self,
        job: Callable[[], Awaitable[None]],
        *,
        interval_minutes: int,
        next_run_time: datetime,
    ) -> None:
        add_job = cast(Callable[..., object], attrgetter("add_job")(self._scheduler))
        _ = add_job(
            job,
            trigger=IntervalTrigger(minutes=interval_minutes, timezone=UTC),
            id=AUTO_SYNC_JOB_ID,
            name="TorBox account auto-sync",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            next_run_time=next_run_time,
        )

    def remove_auto_sync(self) -> None:
        get_job = cast(Callable[[str], object | None], attrgetter("get_job")(self._scheduler))
        if get_job(AUTO_SYNC_JOB_ID) is None:
            return
        remove_job = cast(Callable[[str], None], attrgetter("remove_job")(self._scheduler))
        with suppress(JobLookupError):
            remove_job(AUTO_SYNC_JOB_ID)

    def schedule_season_completion(
        self,
        job: Callable[[], Awaitable[None]],
        *,
        interval_days: int,
        next_run_time: datetime,
    ) -> None:
        add_job = cast(Callable[..., object], attrgetter("add_job")(self._scheduler))
        _ = add_job(
            job,
            trigger=IntervalTrigger(days=interval_days, timezone=UTC),
            id=SEASON_COMPLETION_JOB_ID,
            name="Season auto-complete",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            next_run_time=next_run_time,
        )

    def remove_season_completion(self) -> None:
        get_job = cast(Callable[[str], object | None], attrgetter("get_job")(self._scheduler))
        if get_job(SEASON_COMPLETION_JOB_ID) is None:
            return
        remove_job = cast(Callable[[str], None], attrgetter("remove_job")(self._scheduler))
        with suppress(JobLookupError):
            remove_job(SEASON_COMPLETION_JOB_ID)


class AutoSyncScheduler:
    def __init__(
        self,
        *,
        session_factory: AsyncSessionFactory,
        settings_provider: Callable[[], Settings] = get_settings,
        backend: SchedulerBackend | None = None,
        sync_runner: SyncRunner = run_torbox_account_sync,
        season_completion_runner: SeasonCompletionRunner = run_season_completion,
    ) -> None:
        self._session_factory = session_factory
        self._settings_provider = settings_provider
        self._backend = backend or ApschedulerBackend()
        self._sync_runner = sync_runner
        self._season_completion_runner = season_completion_runner
        self._season_completion_enabled: bool | None = None

    async def start(self) -> None:
        if not self._backend.running:
            self._backend.start()
        await self.reschedule_from_settings()

    async def shutdown(self) -> None:
        if self._backend.running:
            self._backend.shutdown()

    async def reschedule_from_settings(self) -> None:
        snapshot = await self._settings_snapshot()
        if not snapshot.torbox_configured:
            self._remove_job()
        else:
            interval_minutes = snapshot.sync_interval_minutes
            self._backend.schedule_auto_sync(
                self.run_once,
                interval_minutes=interval_minutes,
                next_run_time=datetime.now(UTC) + timedelta(minutes=interval_minutes),
            )
        self._reschedule_season_completion(snapshot)

    async def run_once(self) -> None:
        settings = self._settings_provider()
        async with self._session_factory() as session:
            try:
                _ = await self._sync_runner(session, settings, source="auto")
            except SyncAlreadyRunningError:
                logger.info("Skipping scheduled sync because another sync is already running.")
            except (SyncConfigurationError, SyncExecutionError) as error:
                logger.warning("Scheduled sync failed: %s", error)
            except Exception:
                logger.exception("Scheduled sync failed unexpectedly.")

    async def run_season_completion_once(self) -> None:
        settings = self._settings_provider()
        async with self._session_factory() as session:
            try:
                _ = await self._season_completion_runner(session, settings)
            except SeasonCompletionAlreadyRunningError:
                logger.info("Skipping season auto-complete because it is already running.")
            except (SyncAlreadyRunningError, SyncConfigurationError, SyncExecutionError) as error:
                logger.warning("Season auto-complete could not refresh the library: %s", error)
            except Exception:
                logger.exception("Season auto-complete failed unexpectedly.")

    async def _settings_snapshot(self) -> SettingsSnapshot:
        settings = self._settings_provider()
        async with self._session_factory() as session:
            return await AppSettingsRepository(session, settings).snapshot_with_env()

    def _remove_job(self) -> None:
        self._backend.remove_auto_sync()

    def _reschedule_season_completion(self, snapshot: SettingsSnapshot) -> None:
        was_enabled = self._season_completion_enabled
        self._season_completion_enabled = snapshot.season_auto_complete_enabled
        if not snapshot.season_auto_complete_enabled:
            self._backend.remove_season_completion()
            return
        next_run_time = datetime.now(UTC)
        if was_enabled is True:
            next_run_time += timedelta(days=snapshot.season_auto_complete_interval_days)
        self._backend.schedule_season_completion(
            self.run_season_completion_once,
            interval_days=snapshot.season_auto_complete_interval_days,
            next_run_time=next_run_time,
        )


async def start_auto_sync_scheduler(app: FastAPI) -> None:
    settings = get_settings()
    if settings.database_url is None:
        logger.info("Auto-sync scheduler is disabled because no database is configured.")
        return
    scheduler = AutoSyncScheduler(session_factory=get_session_factory())
    app.state.auto_sync_scheduler = scheduler
    try:
        await scheduler.start()
    except Exception:
        logger.exception("Auto-sync scheduler failed to start.")


async def shutdown_auto_sync_scheduler(app: FastAPI) -> None:
    scheduler = getattr(app.state, "auto_sync_scheduler", None)
    if isinstance(scheduler, AutoSyncScheduler):
        await scheduler.shutdown()


async def reschedule_auto_sync_scheduler(app: FastAPI) -> None:
    scheduler = getattr(app.state, "auto_sync_scheduler", None)
    if isinstance(scheduler, AutoSyncScheduler):
        try:
            await scheduler.reschedule_from_settings()
        except Exception:
            logger.exception("Auto-sync scheduler failed to reschedule.")
