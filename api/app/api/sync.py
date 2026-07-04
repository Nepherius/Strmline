from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.dependencies import get_db_session
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


def _response(summary: SyncRunSummary) -> SyncRunResponse:
    return SyncRunResponse.model_validate(summary, from_attributes=True)
