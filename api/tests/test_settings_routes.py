from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from typing import Any

import httpx
import pytest

from app.api.settings import get_settings_repository
from app.db.repositories.settings import AppSettingsUpdate, SettingsSnapshot
from app.main import create_app


class FakeSettingsRepository:
    def __init__(self) -> None:
        self.snapshot = SettingsSnapshot(
            base_url="http://strmline.test",
            library_root="/library",
            torbox_configured=True,
            tmdb_configured=False,
            resolver_configured=True,
        )
        self.saved_update: AppSettingsUpdate | None = None

    async def snapshot_with_env(self) -> SettingsSnapshot:
        return self.snapshot

    async def save(self, update: AppSettingsUpdate) -> SettingsSnapshot:
        self.saved_update = update
        self.snapshot = replace(
            self.snapshot,
            base_url=update.base_url or self.snapshot.base_url,
            library_root=update.library_root or self.snapshot.library_root,
            torbox_configured=update.torbox_api_key is not None or self.snapshot.torbox_configured,
            tmdb_configured=update.tmdb_api_key is not None or self.snapshot.tmdb_configured,
            resolver_configured=update.resolver_token is not None
            or self.snapshot.resolver_configured,
        )
        return self.snapshot


@pytest.mark.asyncio
async def test_settings_route_returns_redacted_configuration() -> None:
    repository = FakeSettingsRepository()
    app = create_app()
    app.dependency_overrides[get_settings_repository] = _repository_override(repository)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/settings")

    assert response.status_code == httpx.codes.OK
    assert response.json() == {
        "base_url": "http://strmline.test",
        "library_root": "/library",
        "torbox_configured": True,
        "tmdb_configured": False,
        "resolver_configured": True,
    }


@pytest.mark.asyncio
async def test_settings_route_saves_secrets_without_returning_them() -> None:
    repository = FakeSettingsRepository()
    app = create_app()
    app.dependency_overrides[get_settings_repository] = _repository_override(repository)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            "/api/settings",
            json={
                "base_url": "http://127.0.0.1:8001",
                "library_root": "/var/lib/strmline-library",
                "torbox_api_key": "torbox-secret",
                "tmdb_api_key": "tmdb-secret",
                "resolver_token": "resolver-secret",
            },
        )

    assert response.status_code == httpx.codes.OK
    assert "secret" not in response.text
    assert repository.saved_update is not None
    assert repository.saved_update.torbox_api_key == "torbox-secret"
    assert response.json()["tmdb_configured"] is True


def _repository_override(repository: FakeSettingsRepository) -> Callable[..., Any]:
    async def override() -> AsyncIterator[FakeSettingsRepository]:
        yield repository

    return override
