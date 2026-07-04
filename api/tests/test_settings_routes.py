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
            movies_enabled=True,
            shows_enabled=True,
            anime_enabled=False,
            torbox_configured=True,
            tmdb_configured=False,
            resolver_configured=True,
            base_url_source="database",
            library_root_source="database",
            torbox_source="environment",
            tmdb_source=None,
            resolver_source="environment",
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
            movies_enabled=(
                update.movies_enabled
                if update.movies_enabled is not None
                else self.snapshot.movies_enabled
            ),
            shows_enabled=(
                update.shows_enabled
                if update.shows_enabled is not None
                else self.snapshot.shows_enabled
            ),
            anime_enabled=(
                update.anime_enabled
                if update.anime_enabled is not None
                else self.snapshot.anime_enabled
            ),
            torbox_configured=update.torbox_api_key is not None or self.snapshot.torbox_configured,
            tmdb_configured=update.tmdb_api_key is not None or self.snapshot.tmdb_configured,
            resolver_configured=update.resolver_token is not None
            or self.snapshot.resolver_configured,
            tmdb_source="database"
            if update.tmdb_api_key is not None
            else self.snapshot.tmdb_source,
        )
        return self.snapshot

    async def clear_saved_setup(self) -> SettingsSnapshot:
        self.snapshot = replace(
            self.snapshot,
            base_url=None,
            library_root=None,
            movies_enabled=True,
            shows_enabled=True,
            anime_enabled=True,
            torbox_configured=False,
            tmdb_configured=False,
            resolver_configured=False,
            base_url_source=None,
            library_root_source=None,
            torbox_source=None,
            tmdb_source=None,
            resolver_source=None,
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
        "movies_enabled": True,
        "shows_enabled": True,
        "anime_enabled": False,
        "torbox_configured": True,
        "tmdb_configured": False,
        "resolver_configured": True,
        "base_url_source": "database",
        "library_root_source": "database",
        "torbox_source": "environment",
        "tmdb_source": None,
        "resolver_source": "environment",
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
                "movies_enabled": True,
                "shows_enabled": False,
                "anime_enabled": True,
                "torbox_api_key": "torbox-secret",
                "tmdb_api_key": "tmdb-secret",
                "resolver_token": "resolver-secret",
            },
        )

    assert response.status_code == httpx.codes.OK
    assert "secret" not in response.text
    assert repository.saved_update is not None
    assert repository.saved_update.torbox_api_key == "torbox-secret"
    assert repository.saved_update.shows_enabled is False
    assert response.json()["tmdb_configured"] is True
    assert response.json()["tmdb_source"] == "database"


@pytest.mark.asyncio
async def test_settings_route_clears_saved_setup() -> None:
    repository = FakeSettingsRepository()
    app = create_app()
    app.dependency_overrides[get_settings_repository] = _repository_override(repository)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.delete("/api/settings")

    assert response.status_code == httpx.codes.OK
    assert response.json()["torbox_source"] is None
    assert response.json()["tmdb_source"] is None
    assert response.json()["resolver_source"] is None
    assert response.json()["anime_enabled"] is True


def _repository_override(repository: FakeSettingsRepository) -> Callable[..., Any]:
    async def override() -> AsyncIterator[FakeSettingsRepository]:
        yield repository

    return override
