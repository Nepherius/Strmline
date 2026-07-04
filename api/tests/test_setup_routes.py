import httpx
import pytest

from app.api import setup as setup_api
from app.core.config import get_settings
from app.main import create_app
from app.providers.tmdb.connection import TmdbConnectionError
from app.providers.torbox.connection import TorBoxConnectionError


@pytest.mark.asyncio
async def test_torbox_connection_test_reports_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_api_key(provider: object, session: object) -> str:
        _ = provider
        _ = session
        return "torbox-secret"

    async def fake_check_torbox_connection(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(setup_api, "_effective_provider_api_key", fake_api_key)
    monkeypatch.setattr(setup_api, "check_torbox_connection", fake_check_torbox_connection)

    response = await _post_torbox_test({"torbox_api_key": "typed-secret"})

    assert response.status_code == httpx.codes.OK
    assert response.json() == {
        "ok": True,
        "message": "TorBox connection succeeded.",
    }
    assert captured["api_key"] == "typed-secret"
    assert "secret" not in response.text


@pytest.mark.asyncio
async def test_torbox_connection_test_reports_missing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_api_key(provider: object, session: object) -> str | None:
        _ = provider
        _ = session
        return None

    monkeypatch.setattr(setup_api, "_effective_provider_api_key", fake_api_key)

    response = await _post_torbox_test()

    assert response.status_code == httpx.codes.OK
    assert response.json() == {
        "ok": False,
        "message": "TorBox API key is not configured.",
    }


@pytest.mark.asyncio
async def test_torbox_connection_test_uses_safe_failure_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_api_key(provider: object, session: object) -> str:
        _ = provider
        _ = session
        return "torbox-secret"

    async def fake_check_torbox_connection(**kwargs: object) -> None:
        _ = kwargs
        raise TorBoxConnectionError("secret rejected")

    monkeypatch.setattr(setup_api, "_effective_provider_api_key", fake_api_key)
    monkeypatch.setattr(setup_api, "check_torbox_connection", fake_check_torbox_connection)

    response = await _post_torbox_test()

    assert response.status_code == httpx.codes.OK
    assert response.json() == {
        "ok": False,
        "message": "TorBox connection failed.",
    }
    assert "secret" not in response.text


@pytest.mark.asyncio
async def test_tmdb_connection_test_reports_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_api_key(provider: object, session: object) -> str:
        _ = provider
        _ = session
        return "tmdb-secret"

    async def fake_check_tmdb_connection(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(setup_api, "_effective_provider_api_key", fake_api_key)
    monkeypatch.setattr(setup_api, "check_tmdb_connection", fake_check_tmdb_connection)

    response = await _post_connection_test("/api/setup/test/tmdb", {"tmdb_api_key": "typed-tmdb"})

    assert response.status_code == httpx.codes.OK
    assert response.json() == {
        "ok": True,
        "message": "TMDB connection succeeded.",
    }
    assert captured["api_key"] == "typed-tmdb"
    assert "secret" not in response.text
    assert "typed-tmdb" not in response.text


@pytest.mark.asyncio
async def test_tmdb_connection_test_reports_missing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_api_key(provider: object, session: object) -> str | None:
        _ = provider
        _ = session
        return None

    monkeypatch.setattr(setup_api, "_effective_provider_api_key", fake_api_key)

    response = await _post_connection_test("/api/setup/test/tmdb")

    assert response.status_code == httpx.codes.OK
    assert response.json() == {
        "ok": False,
        "message": "TMDB API key is not configured.",
    }


@pytest.mark.asyncio
async def test_tmdb_connection_test_uses_safe_failure_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_api_key(provider: object, session: object) -> str:
        _ = provider
        _ = session
        return "tmdb-secret"

    async def fake_check_tmdb_connection(**kwargs: object) -> None:
        _ = kwargs
        raise TmdbConnectionError("secret rejected")

    monkeypatch.setattr(setup_api, "_effective_provider_api_key", fake_api_key)
    monkeypatch.setattr(setup_api, "check_tmdb_connection", fake_check_tmdb_connection)

    response = await _post_connection_test("/api/setup/test/tmdb")

    assert response.status_code == httpx.codes.OK
    assert response.json() == {
        "ok": False,
        "message": "TMDB connection failed.",
    }
    assert "secret" not in response.text


@pytest.mark.asyncio
async def test_setup_status_does_not_require_resolver_fields_in_direct_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRMLINE_PLAYBACK_MODE", "direct")
    get_settings.cache_clear()

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/setup/status")

    get_settings.cache_clear()
    assert response.status_code == httpx.codes.OK
    assert "base_url" not in response.json()["missing"]
    assert "resolver_token" not in response.json()["missing"]


async def _post_torbox_test(payload: dict[str, str] | None = None) -> httpx.Response:
    return await _post_connection_test("/api/setup/test/torbox", payload)


async def _post_connection_test(
    path: str,
    payload: dict[str, str] | None = None,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post(path, json=payload or {})
