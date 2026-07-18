# pyright: reportMissingTypeStubs=false

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta

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


SyncRunner = Callable[..., Awaitable[object]]
SeasonCompletionRunner = Callable[..., Awaitable[object]]
AsyncSessionFactory = Callable[[], AsyncSession]


class AutoSyncScheduler:
    def __init__(
        self,
        *,
        session_factory: AsyncSessionFactory,
        settings_provider: Callable[[], Settings] = get_settings,
        scheduler: AsyncIOScheduler | None = None,
        sync_runner: SyncRunner = run_torbox_account_sync,
        season_completion_runner: SeasonCompletionRunner = run_season_completion,
    ) -> None:
        self._session_factory = session_factory
        self._settings_provider = settings_provider
        self._scheduler = scheduler or AsyncIOScheduler(timezone=UTC)
        self._sync_runner = sync_runner
        self._season_completion_runner = season_completion_runner
        self._season_completion_enabled: bool | None = None

    async def start(self) -> None:
        if not self._scheduler.running:  # pyright: ignore[reportUnknownMemberType]
            self._scheduler.start()  # pyright: ignore[reportUnknownMemberType]
        await self.reschedule_from_settings()

    async def shutdown(self) -> None:
        if self._scheduler.running:  # pyright: ignore[reportUnknownMemberType]
            self._scheduler.shutdown(wait=False)  # pyright: ignore[reportUnknownMemberType]

    async def reschedule_from_settings(self) -> None:
        snapshot = await self._settings_snapshot()
        if not snapshot.torbox_configured:
            logger.debug("Automatic TorBox sync is disabled because TorBox is not configured.")
            self._remove_job()
        else:
            interval_minutes = snapshot.sync_interval_minutes
            logger.debug(
                "Scheduling automatic TorBox sync every %d minute(s).",
                interval_minutes,
            )
            self._schedule_job(
                AUTO_SYNC_JOB_ID,
                "TorBox account auto-sync",
                self.run_once,
                IntervalTrigger(minutes=interval_minutes, timezone=UTC),
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
        self._remove_scheduled_job(AUTO_SYNC_JOB_ID)

    def _reschedule_season_completion(self, snapshot: SettingsSnapshot) -> None:
        was_enabled = self._season_completion_enabled
        self._season_completion_enabled = snapshot.season_auto_complete_enabled
        if not snapshot.season_auto_complete_enabled:
            logger.debug("Season auto-complete scheduling is disabled.")
            self._remove_scheduled_job(SEASON_COMPLETION_JOB_ID)
            return
        next_run_time = datetime.now(UTC)
        if was_enabled is True:
            next_run_time += timedelta(days=snapshot.season_auto_complete_interval_days)
        logger.debug(
            "Scheduling season auto-complete every %d day(s), checking %d show(s) per minute.",
            snapshot.season_auto_complete_interval_days,
            snapshot.season_auto_complete_shows_per_minute,
        )
        self._schedule_job(
            SEASON_COMPLETION_JOB_ID,
            "Season auto-complete",
            self.run_season_completion_once,
            IntervalTrigger(
                days=snapshot.season_auto_complete_interval_days,
                timezone=UTC,
            ),
            next_run_time=next_run_time,
        )

    def _schedule_job(
        self,
        job_id: str,
        name: str,
        job: Callable[[], Awaitable[None]],
        trigger: IntervalTrigger,
        *,
        next_run_time: datetime,
    ) -> None:
        _ = self._scheduler.add_job(  # pyright: ignore[reportUnknownMemberType]
            job,
            trigger=trigger,
            id=job_id,
            name=name,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            next_run_time=next_run_time,
        )

    def _remove_scheduled_job(self, job_id: str) -> None:
        if self._scheduler.get_job(job_id) is None:  # pyright: ignore[reportUnknownMemberType]
            return
        with suppress(JobLookupError):
            self._scheduler.remove_job(job_id)  # pyright: ignore[reportUnknownMemberType]


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
