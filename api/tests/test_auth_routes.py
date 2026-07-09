# pyright: reportPrivateUsage=false
# pyright: reportUnknownMemberType=false
# pyright: reportOptionalMemberAccess=false
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from argon2 import PasswordHasher
from fastapi import FastAPI

from app.api import auth as auth_module
from app.api.settings import get_settings_repository
from app.core.config import get_settings
from app.db.dependencies import get_db_session, get_optional_db_session
from app.db.models import User
from app.main import create_app

ph = PasswordHasher()

# Apply the fake_settings fixture to all tests in this module
pytestmark = pytest.mark.usefixtures("fake_settings")


class FakeResult:
    def __init__(self, scalar: object | None = None) -> None:
        self._scalar = scalar

    def scalar_one_or_none(self) -> object | None:
        return self._scalar


class FakeSession:
    def __init__(self, user: User | None = None) -> None:
        self.user = user
        self.added: list[object] = []
        self.committed = False
        self.refreshed = False

    async def execute(self, statement: object) -> FakeResult:
        _ = statement
        return FakeResult(scalar=self.user)

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, instance: object) -> None:
        self.refreshed = True
        if isinstance(instance, User):
            instance.id = 1


class FakeSettingsRepository:
    async def snapshot_with_env(self) -> object:
        return type(
            "Snapshot",
            (),
            {
                "base_url": "http://strmline.test",
                "library_root": "/library",
                "movies_enabled": True,
                "shows_enabled": True,
                "anime_enabled": True,
                "playback_mode": "resolver",
                "sync_interval_minutes": 360,
                "torbox_configured": True,
                "tmdb_configured": False,
                "resolver_configured": True,
                "aiostreams_configured": False,
                "base_url_source": "database",
                "library_root_source": "database",
                "torbox_source": "environment",
                "tmdb_source": None,
                "resolver_source": "environment",
                "aiostreams_source": None,
            },
        )()

    async def save(self, update: object) -> object:
        _ = update
        return await self.snapshot_with_env()


def override_session(app: FastAPI, session: object) -> None:
    app.dependency_overrides[get_db_session] = lambda: session
    app.dependency_overrides[get_optional_db_session] = lambda: session


@pytest.fixture
def fake_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRMLINE_APP_SECRET_KEY", "test-secret-key-1234567890-test-secret-key")
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_setup_first_user_success() -> None:
    session = FakeSession(None)

    app = create_app()
    override_session(app, session)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/auth/setup",
            json={"username": "newadmin", "password": "supersecurepassword"},
        )

    assert response.status_code == httpx.codes.OK
    payload = response.json()
    assert payload["username"] == "newadmin"
    assert "id" in payload
    assert session.committed is True
    assert session.refreshed is True

    cookies = response.cookies
    assert "strmline_session" in cookies
    token = cookies["strmline_session"]

    settings = get_settings()
    decoded = jwt.decode(token, settings.app_secret_key.get_secret_value(), algorithms=["HS256"])
    assert decoded["sub"] == "1"


@pytest.mark.asyncio
async def test_setup_first_user_already_exists() -> None:
    existing_user = User(username="existing", hashed_password="hashed")  # noqa: S106
    session = FakeSession(existing_user)

    app = create_app()
    override_session(app, session)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/auth/setup",
            json={"username": "newadmin", "password": "supersecurepassword"},
        )

    assert response.status_code == httpx.codes.BAD_REQUEST
    assert "already exists" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_success() -> None:
    password = "correctpassword"  # noqa: S105
    hashed = ph.hash(password)
    user = User(username="admin", hashed_password=hashed)
    user.id = 42

    session = FakeSession(user)

    app = create_app()
    override_session(app, session)
    auth_module._login_attempts.clear()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": password},
        )

    assert response.status_code == httpx.codes.OK
    assert response.json()["username"] == "admin"
    assert response.json()["id"] == 42
    assert "strmline_session" in response.cookies


@pytest.mark.asyncio
async def test_login_invalid_password() -> None:
    hashed = ph.hash("correctpassword")
    user = User(username="admin", hashed_password=hashed)

    session = FakeSession(user)

    app = create_app()
    override_session(app, session)
    auth_module._login_attempts.clear()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrongpassword"},
        )

    assert response.status_code == httpx.codes.UNAUTHORIZED


@pytest.mark.asyncio
async def test_login_rate_limiting() -> None:
    session = FakeSession(None)
    app = create_app()
    override_session(app, session)

    auth_module._login_attempts["127.0.0.1"] = [
        datetime.now(UTC),
        datetime.now(UTC),
        datetime.now(UTC),
        datetime.now(UTC),
        datetime.now(UTC),
    ]

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrongpassword"},
        )

    assert response.status_code == httpx.codes.TOO_MANY_REQUESTS
    assert "Too many failed login attempts" in response.json()["detail"]
    auth_module._login_attempts.clear()


@pytest.mark.asyncio
async def test_logout() -> None:
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/auth/logout")

    assert response.status_code == httpx.codes.OK
    cookie_headers = list(response.headers.get_list("set-cookie"))
    assert any(
        "strmline_session=;" in h or 'strmline_session=""' in h or "max-age=0" in h.lower()
        for h in cookie_headers
    )


@pytest.mark.asyncio
async def test_get_me_authenticated() -> None:
    user = User(username="admin", hashed_password="hashed")  # noqa: S106
    user.id = 123

    session = FakeSession(user)

    app = create_app()
    override_session(app, session)

    settings = get_settings()
    token = jwt.encode(
        {"sub": "123", "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp())},
        settings.app_secret_key.get_secret_value(),
        algorithm="HS256",
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", cookies={"strmline_session": token}
    ) as client:
        response = await client.get("/api/auth/me")

    assert response.status_code == httpx.codes.OK
    assert response.json()["username"] == "admin"
    assert response.json()["id"] == 123


@pytest.mark.asyncio
async def test_csrf_protection_fails_on_post_without_header() -> None:
    user = User(username="admin", hashed_password="hashed")  # noqa: S106
    user.id = 123

    session = FakeSession(user)

    app = create_app()
    override_session(app, session)
    app.dependency_overrides[get_settings_repository] = FakeSettingsRepository

    settings = get_settings()
    token = jwt.encode(
        {"sub": "123", "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp())},
        settings.app_secret_key.get_secret_value(),
        algorithm="HS256",
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", cookies={"strmline_session": token}
    ) as client:
        response = await client.put(
            "/api/settings",
            json={"movies_enabled": True},
        )

    assert response.status_code == httpx.codes.FORBIDDEN
    assert "CSRF validation failed" in response.json()["detail"]


@pytest.mark.asyncio
async def test_csrf_protection_succeeds_with_header() -> None:
    admin_user = User(username="admin", hashed_password="hashed")  # noqa: S106
    admin_user.id = 123

    session = FakeSession(admin_user)

    app = create_app()
    override_session(app, session)
    app.dependency_overrides[get_settings_repository] = FakeSettingsRepository

    settings = get_settings()
    token = jwt.encode(
        {"sub": "123", "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp())},
        settings.app_secret_key.get_secret_value(),
        algorithm="HS256",
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", cookies={"strmline_session": token}
    ) as client:
        response = await client.put(
            "/api/settings",
            json={"movies_enabled": True},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

    assert response.status_code == httpx.codes.OK
