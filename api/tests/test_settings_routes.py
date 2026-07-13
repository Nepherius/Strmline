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
            playback_mode="resolver",
            sync_interval_minutes=360,
            torbox_configured=True,
            tmdb_configured=False,
            resolver_configured=True,
            aiostreams_configured=False,
            base_url_source="database",
            library_root_source="database",
            torbox_source="environment",
            tmdb_source=None,
            resolver_source="environment",
            aiostreams_source=None,
        )
        self.saved_update: AppSettingsUpdate | None = None

    async def snapshot_with_env(self) -> SettingsSnapshot:
        return self.snapshot

    async def save(self, update: AppSettingsUpdate) -> SettingsSnapshot:
        self.saved_update = update
        self.snapshot = replace(
            self.snapshot,
            base_url=update.base_url or self.snapshot.base_url,
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
            playback_mode=(
                update.playback_mode
                if update.playback_mode is not None
                else self.snapshot.playback_mode
            ),
            sync_interval_minutes=(
                update.sync_interval_minutes
                if update.sync_interval_minutes is not None
                else self.snapshot.sync_interval_minutes
            ),
            debug_logging=(
                update.debug_logging
                if update.debug_logging is not None
                else self.snapshot.debug_logging
            ),
            season_auto_complete_enabled=(
                update.season_auto_complete_enabled
                if update.season_auto_complete_enabled is not None
                else self.snapshot.season_auto_complete_enabled
            ),
            season_auto_complete_interval_days=(
                update.season_auto_complete_interval_days
                if update.season_auto_complete_interval_days is not None
                else self.snapshot.season_auto_complete_interval_days
            ),
            season_auto_complete_allow_uncached=(
                update.season_auto_complete_allow_uncached
                if update.season_auto_complete_allow_uncached is not None
                else self.snapshot.season_auto_complete_allow_uncached
            ),
            season_auto_complete_shows_per_minute=(
                update.season_auto_complete_shows_per_minute
                if update.season_auto_complete_shows_per_minute is not None
                else self.snapshot.season_auto_complete_shows_per_minute
            ),
            torbox_configured=update.torbox_api_key is not None or self.snapshot.torbox_configured,
            tmdb_configured=update.tmdb_api_key is not None or self.snapshot.tmdb_configured,
            resolver_configured=update.resolver_token is not None
            or self.snapshot.resolver_configured,
            aiostreams_configured=update.aiostreams_base_url is not None
            or self.snapshot.aiostreams_configured,
            tmdb_source="database"
            if update.tmdb_api_key is not None
            else self.snapshot.tmdb_source,
            aiostreams_source="database"
            if update.aiostreams_base_url is not None
            else self.snapshot.aiostreams_source,
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
            playback_mode="resolver",
            sync_interval_minutes=360,
            debug_logging=False,
            season_auto_complete_enabled=False,
            season_auto_complete_interval_days=1,
            season_auto_complete_allow_uncached=False,
            season_auto_complete_shows_per_minute=1,
            torbox_configured=False,
            tmdb_configured=False,
            resolver_configured=False,
            aiostreams_configured=False,
            base_url_source=None,
            library_root_source=None,
            torbox_source=None,
            tmdb_source=None,
            resolver_source=None,
            aiostreams_source=None,
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
        "playback_mode": "resolver",
        "sync_interval_minutes": 360,
        "debug_logging": False,
        "season_auto_complete_enabled": False,
        "season_auto_complete_interval_days": 1,
        "season_auto_complete_allow_uncached": False,
        "season_auto_complete_shows_per_minute": 1,
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
                "movies_enabled": True,
                "shows_enabled": False,
                "anime_enabled": True,
                "playback_mode": "direct",
                "sync_interval_minutes": 120,
                "debug_logging": True,
                "season_auto_complete_enabled": True,
                "season_auto_complete_interval_days": 3,
                "season_auto_complete_allow_uncached": True,
                "season_auto_complete_shows_per_minute": 2,
                "torbox_api_key": "torbox-secret",
                "tmdb_api_key": "tmdb-secret",
                "resolver_token": "resolver-secret",
                "aiostreams_base_url": "https://aio.example/manifest.json",
            },
        )

    assert response.status_code == httpx.codes.OK
    assert "secret" not in response.text
    assert "aio.example" not in response.text
    assert repository.saved_update is not None
    assert repository.saved_update.torbox_api_key == "torbox-secret"
    assert repository.saved_update.aiostreams_base_url == "https://aio.example/manifest.json"
    assert repository.saved_update.shows_enabled is False
    assert repository.saved_update.playback_mode == "direct"
    assert repository.saved_update.sync_interval_minutes == 120
    assert repository.saved_update.debug_logging is True
    assert repository.saved_update.season_auto_complete_enabled is True
    assert repository.saved_update.season_auto_complete_interval_days == 3
    assert repository.saved_update.season_auto_complete_allow_uncached is True
    assert repository.saved_update.season_auto_complete_shows_per_minute == 2
    assert response.json()["tmdb_configured"] is True
    assert response.json()["tmdb_source"] == "database"
    assert response.json()["aiostreams_configured"] is True
    assert response.json()["aiostreams_source"] == "database"


@pytest.mark.asyncio
async def test_settings_route_rejects_invalid_numeric_settings() -> None:
    repository = FakeSettingsRepository()
    app = create_app()
    app.dependency_overrides[get_settings_repository] = _repository_override(repository)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            "/api/settings",
            json={"sync_interval_minutes": 0},
        )

    assert response.status_code == httpx.codes.UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_settings_route_rejects_invalid_season_completion_rate() -> None:
    repository = FakeSettingsRepository()
    app = create_app()
    app.dependency_overrides[get_settings_repository] = _repository_override(repository)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            "/api/settings",
            json={"season_auto_complete_shows_per_minute": 0},
        )

    assert response.status_code == httpx.codes.UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_settings_route_rejects_invalid_playback_mode() -> None:
    repository = FakeSettingsRepository()
    app = create_app()
    app.dependency_overrides[get_settings_repository] = _repository_override(repository)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            "/api/settings",
            json={"playback_mode": "proxy"},
        )

    assert response.status_code == httpx.codes.UNPROCESSABLE_ENTITY


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
    assert response.json()["aiostreams_source"] is None
    assert response.json()["anime_enabled"] is True


def _repository_override(repository: FakeSettingsRepository) -> Callable[..., Any]:
    async def override() -> AsyncIterator[FakeSettingsRepository]:
        yield repository

    return override
