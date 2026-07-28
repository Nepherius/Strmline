# pyright: reportMissingTypeStubs=false

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
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
from app.sync.item_service import run_torbox_item_sync
from app.sync.service import (
    SyncAlreadyRunningError,
    SyncConfigurationError,
    SyncExecutionError,
    run_torbox_account_sync,
)

AUTO_SYNC_JOB_ID = "torbox-auto-sync"
QUEUED_SYNC_JOB_ID = "torbox-queued-sync"
SEASON_COMPLETION_JOB_ID = "season-auto-complete"
QUEUED_SYNC_RETRY_SECONDS = 2

logger = logging.getLogger(__name__)


SyncRunner = Callable[..., Awaitable[object]]
ItemSyncRunner = Callable[..., Awaitable[object]]
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
        item_sync_runner: ItemSyncRunner = run_torbox_item_sync,
        season_completion_runner: SeasonCompletionRunner = run_season_completion,
    ) -> None:
        self._session_factory = session_factory
        self._settings_provider = settings_provider
        self._scheduler = scheduler or AsyncIOScheduler(timezone=UTC)
        self._sync_runner = sync_runner
        self._item_sync_runner = item_sync_runner
        self._season_completion_runner = season_completion_runner
        self._season_completion_enabled: bool | None = None
        self._pending_torrent_ids: set[str] = set()
        self._full_sync_requested = False
        self._queued_worker_running = False

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

    def enqueue_post_add_sync(self, torrent_id: str | None) -> bool:
        """Queue immediate work without retaining the request's database session."""
        if not self._scheduler.running:  # pyright: ignore[reportUnknownMemberType]
            return False
        if torrent_id is None:
            self._full_sync_requested = True
        else:
            self._pending_torrent_ids.add(torrent_id)
        if not self._queued_worker_running:
            self._schedule_queued_sync()
        return True

    async def run_queued_syncs(self) -> None:
        retry_delay = 0
        self._queued_worker_running = True
        try:
            while self._full_sync_requested or self._pending_torrent_ids:
                if self._full_sync_requested:
                    self._full_sync_requested = False
                    self._pending_torrent_ids.clear()
                    completed = await self._run_queued_full_sync()
                    if not completed:
                        self._full_sync_requested = True
                        retry_delay = QUEUED_SYNC_RETRY_SECONDS
                        return
                    continue

                torrent_id = self._pending_torrent_ids.pop()
                completed = await self._run_queued_item_sync(torrent_id)
                if not completed:
                    self._pending_torrent_ids.add(torrent_id)
                    retry_delay = QUEUED_SYNC_RETRY_SECONDS
                    return
        finally:
            self._queued_worker_running = False
            if self._full_sync_requested or self._pending_torrent_ids:
                self._schedule_queued_sync(delay_seconds=retry_delay)

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

    async def _run_queued_full_sync(self) -> bool:
        settings = self._settings_provider()
        async with self._session_factory() as session:
            try:
                _ = await self._sync_runner(session, settings, source="auto")
            except SyncAlreadyRunningError:
                return False
            except (SyncConfigurationError, SyncExecutionError) as error:
                logger.warning("Queued full sync failed: %s", error)
            except Exception:
                logger.exception("Queued full sync failed unexpectedly.")
        return True

    async def _run_queued_item_sync(self, torrent_id: str) -> bool:
        settings = self._settings_provider()
        async with self._session_factory() as session:
            try:
                _ = await self._item_sync_runner(
                    session,
                    settings,
                    torrent_id=torrent_id,
                )
            except SyncAlreadyRunningError:
                return False
            except (SyncConfigurationError, SyncExecutionError) as error:
                logger.warning(
                    "Queued TorBox item sync failed item_id=%s: %s",
                    torrent_id,
                    error,
                )
            except Exception:
                logger.exception(
                    "Queued TorBox item sync failed unexpectedly item_id=%s.",
                    torrent_id,
                )
        return True

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

    def _schedule_queued_sync(self, *, delay_seconds: int = 0) -> None:
        run_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)
        _ = self._scheduler.add_job(  # pyright: ignore[reportUnknownMemberType]
            self.run_queued_syncs,
            trigger=DateTrigger(run_date=run_at, timezone=UTC),
            id=QUEUED_SYNC_JOB_ID,
            name="Queued TorBox item sync",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=30,
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


def enqueue_post_add_sync(app: FastAPI, torrent_id: str | None) -> bool:
    scheduler = getattr(app.state, "auto_sync_scheduler", None)
    if not isinstance(scheduler, AutoSyncScheduler):
        return False
    return scheduler.enqueue_post_add_sync(torrent_id)
