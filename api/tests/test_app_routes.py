import httpx
import pytest

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
