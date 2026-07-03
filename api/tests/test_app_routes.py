from pathlib import Path

import httpx
import pytest

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
