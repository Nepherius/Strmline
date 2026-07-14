import httpx
import pytest

from app.core.config import get_settings
from app.main import create_app


@pytest.mark.asyncio
async def test_docs_and_openapi_are_disabled_without_debug_logging() -> None:
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        docs_response = await client.get("/docs")
        openapi_response = await client.get("/openapi.json")

    assert docs_response.status_code == httpx.codes.NOT_FOUND
    assert openapi_response.status_code == httpx.codes.NOT_FOUND


@pytest.mark.asyncio
async def test_docs_csp_allows_swagger_assets_when_debug_logging_is_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRMLINE_DEBUG_LOGGING", "true")
    get_settings.cache_clear()
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/docs")

    get_settings.cache_clear()
    csp = response.headers["content-security-policy"]
    assert response.status_code == httpx.codes.OK
    assert "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'" in csp
    assert "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'" in csp
    assert "https://fastapi.tiangolo.com" in csp
