from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.dependencies import get_db_session
from app.db.repositories.sync_runs import SyncRunRecord, SyncRunRepository
from app.sync.service import (
    SyncAlreadyRunningError,
    SyncConfigurationError,
    SyncExecutionError,
    SyncRunSummary,
    run_torbox_account_sync,
)

router = APIRouter(prefix="/api/sync", tags=["sync"])


class SyncRunResponse(BaseModel):
    sync_run_id: int
    playback_mode: str
    library_root: str
    scanned_files: int
    written_files: int
    skipped_files: int


class SyncRunStatusResponse(BaseModel):
    id: int
    status: str
    source: str
    started_at: str
    finished_at: str | None
    scanned_count: int
    written_count: int
    skipped_count: int


class SyncErrorResponse(BaseModel):
    id: int
    sync_run_id: int
    phase: str
    item_ref: str | None
    message: str
    created_at: str


class SyncStatusResponse(BaseModel):
    last_run: SyncRunStatusResponse | None
    last_auto_run: SyncRunStatusResponse | None
    recent_errors: list[SyncErrorResponse]


@router.post("/run", response_model=SyncRunResponse)
async def run_sync_now(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SyncRunResponse:
    try:
        summary = await run_torbox_account_sync(session, get_settings())
    except SyncAlreadyRunningError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except SyncConfigurationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except SyncExecutionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return _response(summary)


@router.get("/status", response_model=SyncStatusResponse)
async def sync_status(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SyncStatusResponse:
    status = await SyncRunRepository(session).status()
    return SyncStatusResponse(
        last_run=_sync_run_response(status.last_run),
        last_auto_run=_sync_run_response(status.last_auto_run),
        recent_errors=[
            SyncErrorResponse(
                id=error.id,
                sync_run_id=error.sync_run_id,
                phase=error.phase,
                item_ref=error.item_ref,
                message=error.message,
                created_at=error.created_at.isoformat(),
            )
            for error in status.recent_errors
        ],
    )


@router.post("/errors/{error_id}/dismiss", status_code=204)
async def dismiss_sync_error(
    error_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    dismissed = await SyncRunRepository(session).dismiss_error(error_id)
    if not dismissed:
        raise HTTPException(status_code=404, detail="Sync error was not found.")
    await session.commit()


def _sync_run_response(run: SyncRunRecord | None) -> SyncRunStatusResponse | None:
    if run is None:
        return None
    return SyncRunStatusResponse(
        id=run.id,
        status=run.status,
        source=run.source,
        started_at=run.started_at.isoformat(),
        finished_at=run.finished_at.isoformat() if run.finished_at is not None else None,
        scanned_count=run.scanned_count,
        written_count=run.written_count,
        skipped_count=run.skipped_count,
    )


def _response(summary: SyncRunSummary) -> SyncRunResponse:
    return SyncRunResponse.model_validate(summary, from_attributes=True)
