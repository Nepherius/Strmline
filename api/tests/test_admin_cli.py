from __future__ import annotations

from typing import cast

import pytest
from argon2 import PasswordHasher
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_cli import MINIMUM_PASSWORD_LENGTH, reset_first_user_password
from app.db.models import User


class FakeResult:
    def __init__(self, user: User | None) -> None:
        self._user = user

    def scalar_one_or_none(self) -> User | None:
        return self._user


class FakeSession:
    def __init__(self, user: User | None) -> None:
        self._user = user
        self.committed = False

    async def execute(self, statement: object) -> FakeResult:
        _ = statement
        return FakeResult(self._user)

    async def commit(self) -> None:
        self.committed = True


@pytest.mark.asyncio
async def test_reset_first_user_password_updates_hash_and_returns_username() -> None:
    user = User(username="admin", hashed_password="old-hash")  # noqa: S106
    session = FakeSession(user)
    password = "new-password"  # noqa: S105

    username = await reset_first_user_password(cast(AsyncSession, session), password)

    assert username == "admin"
    assert session.committed is True
    assert PasswordHasher().verify(user.hashed_password, password) is True


@pytest.mark.asyncio
async def test_reset_first_user_password_reports_missing_user() -> None:
    session = FakeSession(None)

    username = await reset_first_user_password(
        cast(AsyncSession, session),
        "new-password",
    )

    assert username is None
    assert session.committed is False


def test_minimum_password_length_matches_setup_requirement() -> None:
    assert MINIMUM_PASSWORD_LENGTH == 8
