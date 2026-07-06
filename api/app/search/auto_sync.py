from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.sync.service import (
    SyncAlreadyRunningError,
    SyncConfigurationError,
    SyncExecutionError,
    SyncRunSummary,
    run_torbox_account_sync,
)


@dataclass(frozen=True, slots=True)
class AutoSyncOutcome:
    status: str
    sync_run_id: int | None
    message: str


async def auto_sync_after_stream_add(
    *,
    session: AsyncSession,
    settings: Settings,
    action_message: str,
) -> AutoSyncOutcome:
    try:
        summary = await run_torbox_account_sync(session, settings)
    except SyncAlreadyRunningError:
        return AutoSyncOutcome(
            status="already_running",
            sync_run_id=None,
            message=f"{action_message} Sync is already running.",
        )
    except (SyncConfigurationError, SyncExecutionError) as error:
        return AutoSyncOutcome(
            status="failed",
            sync_run_id=None,
            message=f"{action_message} Automatic sync failed: {error}",
        )
    return AutoSyncOutcome(
        status="success",
        sync_run_id=summary.sync_run_id,
        message=_synced_message(action_message, summary),
    )


def _synced_message(action_message: str, summary: SyncRunSummary) -> str:
    return (
        f"{action_message} Synced library: "
        f"{summary.written_files} written, {summary.skipped_files} skipped."
    )
