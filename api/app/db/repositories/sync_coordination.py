from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

SYNC_ADVISORY_LOCK_ID = 8_357_264_913


class SyncCoordinationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def try_lock(self) -> bool:
        result = await self._session.execute(
            select(func.pg_try_advisory_lock(SYNC_ADVISORY_LOCK_ID))
        )
        return bool(result.scalar_one())

    async def release(self) -> None:
        _ = await self._session.execute(select(func.pg_advisory_unlock(SYNC_ADVISORY_LOCK_ID)))
