from base64 import b64encode
from hashlib import sha256
from pathlib import Path

import httpx
import pytest

from app.core.config import get_settings
from app.main import create_app


@pytest.mark.asyncio
async def test_static_ui_serves_favicon_and_index_for_application_routes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bootstrap_script = "window.strmline = true;"
    _ = (tmp_path / "index.html").write_text(
        f"<main>Strmline UI</main><script>{bootstrap_script}</script>", encoding="utf-8"
    )
    _ = (tmp_path / "favicon.svg").write_text("<svg></svg>", encoding="utf-8")
    monkeypatch.setenv("STRMLINE_STATIC_DIR", str(tmp_path))
    get_settings.cache_clear()

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        root_response = await client.get("/")
        favicon_response = await client.get("/favicon.svg")
        setup_response = await client.get("/setup")
        api_response = await client.get("/api/not-found")

    get_settings.cache_clear()
    assert root_response.status_code == httpx.codes.OK
    assert "Strmline UI" in root_response.text
    expected_hash = b64encode(sha256(bootstrap_script.encode("utf-8")).digest()).decode("ascii")
    assert f"script-src 'self' 'sha256-{expected_hash}'" in root_response.headers[
        "content-security-policy"
    ]
    assert favicon_response.status_code == httpx.codes.OK
    assert favicon_response.headers["content-type"] == "image/svg+xml"
    assert setup_response.status_code == httpx.codes.OK
    assert "Strmline UI" in setup_response.text
    assert api_response.status_code == httpx.codes.NOT_FOUND
