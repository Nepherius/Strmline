from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.dependencies import get_db_session
from app.db.repositories.error_log import ErrorLogRepository

router = APIRouter(prefix="/api/logs", tags=["logs"])


class ErrorLogResponse(BaseModel):
    id: int
    logger_name: str
    message: str
    created_at: str


@router.get("/errors", response_model=list[ErrorLogResponse])
async def recent_error_logs(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[ErrorLogResponse]:
    records = await ErrorLogRepository(session).recent(limit=limit)
    return [
        ErrorLogResponse(
            id=record.id,
            logger_name=record.logger_name,
            message=record.message,
            created_at=record.created_at.isoformat(),
        )
        for record in records
    ]
