from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.sync_coordination import SyncCoordinationRepository


class FakeResult:
    def scalar_one(self) -> bool:
        return True


class FakeSession:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, statement: object) -> FakeResult:
        _ = statement
        self.calls += 1
        return FakeResult()


@pytest.mark.asyncio
async def test_database_sync_lock_is_acquired_and_explicitly_released() -> None:
    session = FakeSession()
    repository = SyncCoordinationRepository(cast(AsyncSession, session))

    assert await repository.try_lock() is True
    await repository.release()

    assert session.calls == 2
