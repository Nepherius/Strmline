from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from app.api import resolver as resolver_api
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
    assert response.headers["cache-control"] == "no-store"


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


@pytest.mark.asyncio
async def test_play_redirects_from_database_resolver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver_api.clear_resolved_target_cache()

    async def fake_token_is_valid(settings: object, token: str, session: object) -> bool:
        _ = settings
        _ = session
        return token == "saved-token"  # noqa: S105

    async def fake_database_target(settings: object, entry_id: str, session: object) -> str:
        _ = settings
        _ = session
        assert entry_id == "entry-id"
        return "https://example.test/final"

    monkeypatch.setattr(resolver_api, "_resolver_token_is_valid", fake_token_is_valid)
    monkeypatch.setattr(resolver_api, "_database_resolver_target", fake_database_target)
    app = create_app()
    app.dependency_overrides[resolver_api.get_optional_db_session] = _fake_database_session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        response = await client.get("/play/entry-id", params={"token": "saved-token"})

    assert response.status_code == httpx.codes.TEMPORARY_REDIRECT
    assert response.headers["location"] == "https://example.test/final"
    assert response.headers["cache-control"] == "no-store"
    resolver_api.clear_resolved_target_cache()


@pytest.mark.asyncio
async def test_play_reuses_short_lived_database_target_for_head_then_get(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver_api.clear_resolved_target_cache()
    resolution_calls = 0

    async def fake_token_is_valid(settings: object, token: str, session: object) -> bool:
        _ = settings
        _ = session
        return token == "saved-token"  # noqa: S105

    async def fake_database_target(settings: object, entry_id: str, session: object) -> str:
        nonlocal resolution_calls
        _ = settings
        _ = session
        assert entry_id == "cached-entry"
        resolution_calls += 1
        return "https://cdn.example.test/temporary"

    monkeypatch.setattr(resolver_api, "_resolver_token_is_valid", fake_token_is_valid)
    monkeypatch.setattr(resolver_api, "_database_resolver_target", fake_database_target)
    app = create_app()
    app.dependency_overrides[resolver_api.get_optional_db_session] = _fake_database_session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        head_response = await client.head("/play/cached-entry", params={"token": "saved-token"})
        get_response = await client.get("/play/cached-entry", params={"token": "saved-token"})

    assert head_response.status_code == httpx.codes.TEMPORARY_REDIRECT
    assert get_response.status_code == httpx.codes.TEMPORARY_REDIRECT
    assert head_response.headers["location"] == "https://cdn.example.test/temporary"
    assert get_response.headers["location"] == "https://cdn.example.test/temporary"
    assert resolution_calls == 1
    resolver_api.clear_resolved_target_cache()


async def _fake_database_session() -> AsyncIterator[object]:
    yield object()


def _set_resolver_env(monkeypatch: pytest.MonkeyPatch, library_root: Path) -> None:
    monkeypatch.setenv("STRMLINE_LIBRARY_ROOT", str(library_root))
    monkeypatch.setenv("STRMLINE_RESOLVER_TOKEN", "secret")
    get_settings.cache_clear()


def test_play_operations_have_unique_openapi_ids() -> None:
    operations = create_app().openapi()["paths"]["/play/{entry_id}"]

    assert operations["get"]["operationId"] == "play"
    assert operations["head"]["operationId"] == "play_head"
