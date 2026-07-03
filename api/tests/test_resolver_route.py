from pathlib import Path

import httpx
import pytest

from app.core.config import get_settings
from app.main import create_app
from app.resolver.manifest import ResolverManifestEntry, write_manifest_entries


@pytest.mark.asyncio
async def test_play_redirects_for_valid_resolver_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = write_manifest_entries(
        tmp_path,
        [ResolverManifestEntry(entry_id="entry-id", target_url="https://example.test/final")],
    )
    _set_resolver_env(monkeypatch, tmp_path)
    app = create_app()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        response = await client.get("/play/entry-id", params={"token": "secret"})

    get_settings.cache_clear()
    assert response.status_code == httpx.codes.TEMPORARY_REDIRECT
    assert response.headers["location"] == "https://example.test/final"


@pytest.mark.asyncio
async def test_play_head_redirects_for_valid_resolver_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = write_manifest_entries(
        tmp_path,
        [ResolverManifestEntry(entry_id="entry-id", target_url="https://example.test/final")],
    )
    _set_resolver_env(monkeypatch, tmp_path)
    app = create_app()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        response = await client.head("/play/entry-id", params={"token": "secret"})

    get_settings.cache_clear()
    assert response.status_code == httpx.codes.TEMPORARY_REDIRECT
    assert response.headers["location"] == "https://example.test/final"


@pytest.mark.asyncio
async def test_play_rejects_invalid_resolver_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = write_manifest_entries(
        tmp_path,
        [ResolverManifestEntry(entry_id="entry-id", target_url="https://example.test/final")],
    )
    _set_resolver_env(monkeypatch, tmp_path)
    app = create_app()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/play/entry-id", params={"token": "wrong"})

    get_settings.cache_clear()
    assert response.status_code == httpx.codes.FORBIDDEN


def _set_resolver_env(monkeypatch: pytest.MonkeyPatch, library_root: Path) -> None:
    monkeypatch.setenv("STRMLINE_LIBRARY_ROOT", str(library_root))
    monkeypatch.setenv("STRMLINE_RESOLVER_TOKEN", "secret")
    get_settings.cache_clear()
