from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Annotated

from anyio.to_thread import run_sync
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.error_logging import read_recent_error_logs

router = APIRouter(prefix="/api/logs", tags=["logs"])


class ErrorLogResponse(BaseModel):
    id: int
    logger_name: str
    message: str
    created_at: str


def get_error_log_dir() -> Path:
    return get_settings().log_dir


@router.get("/errors", response_model=list[ErrorLogResponse])
async def recent_error_logs(
    log_dir: Annotated[Path, Depends(get_error_log_dir)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[ErrorLogResponse]:
    records = await run_sync(partial(read_recent_error_logs, log_dir, limit=limit))
    return [
        ErrorLogResponse(
            id=index,
            logger_name=record.logger_name,
            message=record.message,
            created_at=record.created_at.isoformat(),
        )
        for index, record in enumerate(records, start=1)
    ]
