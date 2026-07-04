from pathlib import Path

import httpx
import pytest

from app.api import library as library_api
from app.core.config import get_settings
from app.main import create_app


@pytest.mark.asyncio
async def test_health_endpoint_returns_service_status() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/health")

    assert response.status_code == httpx.codes.OK
    assert response.json() == {
        "service": "Strmline",
        "status": "ok",
        "version": "0.1.0",
    }


@pytest.mark.asyncio
async def test_setup_status_reports_missing_required_settings() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/setup/status")

    assert response.status_code == httpx.codes.OK
    assert response.json() == {
        "configured": False,
        "missing": [
            "base_url",
            "database_url",
            "library_root",
            "tmdb_api_key",
            "torbox_api_key",
        ],
    }


@pytest.mark.asyncio
async def test_library_summary_reports_configured_library(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    library_file = tmp_path / "movies" / "Movie One (2024)" / "Movie One (2024).strm"
    library_file.parent.mkdir(parents=True)
    _ = library_file.write_text("https://example.test/video\n", encoding="utf-8")
    monkeypatch.setenv("STRMLINE_BASE_URL", "http://strmline.test")
    monkeypatch.setenv("STRMLINE_DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("STRMLINE_LIBRARY_ROOT", str(tmp_path))
    monkeypatch.setenv("STRMLINE_TMDB_API_KEY", "tmdb")
    monkeypatch.setenv("STRMLINE_TORBOX_API_KEY", "torbox")
    get_settings.cache_clear()

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/library/summary")

    get_settings.cache_clear()
    assert response.status_code == httpx.codes.OK
    payload = response.json()
    assert payload["configured"] is True
    assert payload["exists"] is True
    assert payload["total_files"] == 1
    assert payload["category_counts"]["movies"] == 1


@pytest.mark.asyncio
async def test_library_root_can_come_from_database_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STRMLINE_LIBRARY_ROOT", raising=False)
    monkeypatch.setenv("STRMLINE_DATABASE_URL", "postgresql://example")
    get_settings.cache_clear()

    monkeypatch.setattr(library_api, "build_session_factory", fake_session_factory)
    monkeypatch.setattr(library_api, "AppSettingsRepository", fake_settings_repository(tmp_path))

    try:
        library_root = await library_api.get_library_root()
    finally:
        get_settings.cache_clear()

    assert library_root == tmp_path


class FakeSessionContext:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        _ = exc_type
        _ = exc
        _ = traceback


def fake_session_factory(database_url: str) -> object:
    _ = database_url

    class FakeSessionFactory:
        def __call__(self) -> FakeSessionContext:
            return FakeSessionContext()

    return FakeSessionFactory()


def fake_settings_repository(library_root: Path) -> object:
    class FakeSettingsRepository:
        def __init__(self, session: object, settings: object) -> None:
            _ = session
            _ = settings

        async def snapshot_with_env(self) -> object:
            return type("Snapshot", (), {"library_root": str(library_root)})()

    return FakeSettingsRepository
