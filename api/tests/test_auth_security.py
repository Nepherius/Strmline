from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from fastapi import FastAPI

from app.core.config import get_settings
from app.db.dependencies import get_db_session, get_optional_db_session
from app.db.models import User
from app.main import create_app

pytestmark = pytest.mark.usefixtures("fake_settings")


class FakeResult:
    def __init__(self, scalar: object | None = None) -> None:
        self._scalar = scalar

    def scalar_one_or_none(self) -> object | None:
        return self._scalar


class FakeSession:
    def __init__(self, user: User | None) -> None:
        self.user = user

    async def execute(self, statement: object) -> FakeResult:
        _ = statement
        return FakeResult(self.user)


@pytest.fixture
def fake_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRMLINE_APP_SECRET_KEY", "test-secret-key-1234567890-test-secret-key")
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_protected_routes_do_not_allow_first_run_anonymous_access() -> None:
    app = create_app()
    override_session(app, FakeSession(None))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/sync/run")

    assert response.status_code == httpx.codes.UNAUTHORIZED


@pytest.mark.asyncio
async def test_setup_provider_tests_require_auth_after_admin_exists() -> None:
    user = User(username="admin", hashed_password="hashed")  # noqa: S106
    user.id = 1
    app = create_app()
    override_session(app, FakeSession(user))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/setup/test/torbox", json={})

    assert response.status_code == httpx.codes.UNAUTHORIZED


@pytest.mark.asyncio
async def test_setup_provider_tests_require_csrf_after_admin_exists() -> None:
    user = User(username="admin", hashed_password="hashed")  # noqa: S106
    user.id = 1
    app = create_app()
    override_session(app, FakeSession(user))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        cookies={
            "strmline_session": signed_session_token(user.id, "csrf-token"),
            "strmline_csrf": "csrf-token",
        },
    ) as client:
        response = await client.post("/api/setup/test/torbox", json={})

    assert response.status_code == httpx.codes.FORBIDDEN


def override_session(app: FastAPI, session: FakeSession) -> None:
    async def session_override() -> AsyncIterator[FakeSession]:
        yield session

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_optional_db_session] = session_override


def signed_session_token(user_id: int, csrf_token: str) -> str:
    settings = get_settings()
    assert settings.app_secret_key is not None
    return jwt.encode(  # pyright: ignore[reportUnknownMemberType]
        {
            "sub": str(user_id),
            "csrf": csrf_token,
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        },
        settings.app_secret_key.get_secret_value(),
        algorithm="HS256",
    )
