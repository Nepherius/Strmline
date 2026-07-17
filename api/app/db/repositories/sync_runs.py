from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SyncError, SyncRun, utc_now
from app.sync.torbox_strm import TorBoxStrmSyncResult

SyncRunSource = Literal["manual", "auto", "season_auto_complete"]


@dataclass(frozen=True, slots=True)
class SyncRunRecord:
    id: int
    status: str
    source: str
    started_at: datetime
    finished_at: datetime | None
    scanned_count: int
    written_count: int
    skipped_count: int


@dataclass(frozen=True, slots=True)
class SyncErrorRecord:
    id: int
    sync_run_id: int
    phase: str
    item_ref: str | None
    message: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SyncStatusSnapshot:
    last_run: SyncRunRecord | None
    last_auto_run: SyncRunRecord | None
    recent_errors: tuple[SyncErrorRecord, ...]


class SyncRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_success(
        self,
        result: TorBoxStrmSyncResult,
        *,
        source: SyncRunSource = "manual",
    ) -> int:
        sync_run = self._run(
            status="partial" if result.partial or result.diagnostics else "success",
            source=source,
            scanned=result.scanned_files,
            written=result.written_files,
            skipped=result.skipped_files,
        )
        await self._session.flush()
        self._session.add_all(
            [
                SyncError(
                    sync_run_id=sync_run.id,
                    phase=diagnostic.phase,
                    item_ref=diagnostic.item_ref,
                    message=diagnostic.message,
                )
                for diagnostic in result.diagnostics
            ]
        )
        return sync_run.id

    async def record_failure(  # noqa: PLR0913
        self,
        *,
        phase: str,
        message: str,
        source: SyncRunSource = "manual",
        item_ref: str | None = None,
        scanned_count: int = 0,
        written_count: int = 0,
        skipped_count: int = 0,
    ) -> int:
        sync_run = self._run(
            status="failed",
            source=source,
            scanned=scanned_count,
            written=written_count,
            skipped=skipped_count,
        )
        await self._session.flush()
        self._session.add(
            SyncError(
                sync_run_id=sync_run.id,
                phase=phase,
                item_ref=item_ref,
                message=message,
            )
        )
        return sync_run.id

    async def record_season_completion(
        self,
        *,
        checked_shows: int,
        missing_episodes: int,
        added_torrents: int,
        diagnostics: tuple[tuple[str | None, str], ...],
    ) -> int:
        sync_run = self._run(
            status="partial" if diagnostics else "success",
            source="season_auto_complete",
            scanned=checked_shows,
            written=added_torrents,
            skipped=missing_episodes,
        )
        await self._session.flush()
        self._session.add_all(
            [
                SyncError(
                    sync_run_id=sync_run.id,
                    phase="season_auto_complete",
                    item_ref=item_ref,
                    message=message,
                )
                for item_ref, message in diagnostics
            ]
        )
        return sync_run.id

    async def status(self, *, error_limit: int = 5) -> SyncStatusSnapshot:
        last_run_result = await self._session.execute(
            select(SyncRun)
            .where(SyncRun.source.in_(("manual", "auto")))
            .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
            .limit(1)
        )
        last_auto_run_result = await self._session.execute(
            select(SyncRun)
            .where(SyncRun.source == "auto")
            .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
            .limit(1)
        )
        errors_result = await self._session.execute(
            select(SyncError)
            .where(SyncError.dismissed_at.is_(None))
            .order_by(SyncError.created_at.desc(), SyncError.id.desc())
            .limit(error_limit)
        )
        last_run = last_run_result.scalar_one_or_none()
        last_auto_run = last_auto_run_result.scalar_one_or_none()
        return SyncStatusSnapshot(
            last_run=_sync_run_record(last_run) if last_run is not None else None,
            last_auto_run=(_sync_run_record(last_auto_run) if last_auto_run is not None else None),
            recent_errors=tuple(_sync_error_record(error) for error in errors_result.scalars()),
        )

    async def dismiss_error(self, error_id: int) -> bool:
        result = await self._session.execute(select(SyncError).where(SyncError.id == error_id))
        sync_error = result.scalar_one_or_none()
        if sync_error is None:
            return False
        if sync_error.dismissed_at is None:
            sync_error.dismissed_at = utc_now()
        return True

    def _run(
        self,
        *,
        status: str,
        source: SyncRunSource,
        scanned: int,
        written: int,
        skipped: int,
    ) -> SyncRun:
        now = utc_now()
        sync_run = SyncRun(
            status=status,
            source=source,
            started_at=now,
            finished_at=now,
            scanned_count=scanned,
            written_count=written,
            skipped_count=skipped,
        )
        self._session.add(sync_run)
        return sync_run


def _sync_run_record(sync_run: SyncRun) -> SyncRunRecord:
    return SyncRunRecord(
        id=sync_run.id,
        status=sync_run.status,
        source=sync_run.source,
        started_at=sync_run.started_at,
        finished_at=sync_run.finished_at,
        scanned_count=sync_run.scanned_count,
        written_count=sync_run.written_count,
        skipped_count=sync_run.skipped_count,
    )


def _sync_error_record(error: SyncError) -> SyncErrorRecord:
    return SyncErrorRecord(
        id=error.id,
        sync_run_id=error.sync_run_id,
        phase=error.phase,
        item_ref=error.item_ref,
        message=error.message,
        created_at=error.created_at,
    )
