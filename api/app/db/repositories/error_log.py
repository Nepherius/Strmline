from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ErrorLog, SyncError


@dataclass(frozen=True, slots=True)
class ErrorLogRecord:
    id: int
    logger_name: str
    message: str
    created_at: datetime


class ErrorLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, *, logger_name: str, message: str) -> None:
        self._session.add(ErrorLog(logger_name=logger_name, message=message))
        await self._session.commit()

    async def recent(self, *, limit: int) -> tuple[ErrorLogRecord, ...]:
        result = await self._session.execute(
            select(ErrorLog).order_by(ErrorLog.created_at.desc(), ErrorLog.id.desc()).limit(limit)
        )
        return tuple(_record(error_log) for error_log in result.scalars())

    async def purge_before(self, cutoff: datetime) -> None:
        _ = await self._session.execute(delete(ErrorLog).where(ErrorLog.created_at < cutoff))
        _ = await self._session.execute(delete(SyncError).where(SyncError.created_at < cutoff))
        await self._session.commit()


def _record(error_log: ErrorLog) -> ErrorLogRecord:
    return ErrorLogRecord(
        id=error_log.id,
        logger_name=error_log.logger_name,
        message=error_log.message,
        created_at=error_log.created_at,
    )
