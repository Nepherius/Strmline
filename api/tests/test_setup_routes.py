import httpx
import pytest

from app.api import setup as setup_api
from app.main import create_app
from app.providers.torbox.connection import TorBoxConnectionError


@pytest.mark.asyncio
async def test_torbox_connection_test_reports_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_api_key() -> str:
        return "torbox-secret"

    async def fake_check_torbox_connection(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(setup_api, "_effective_torbox_api_key", fake_api_key)
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
    async def fake_api_key() -> str | None:
        return None

    monkeypatch.setattr(setup_api, "_effective_torbox_api_key", fake_api_key)

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
    async def fake_api_key() -> str:
        return "torbox-secret"

    async def fake_check_torbox_connection(**kwargs: object) -> None:
        _ = kwargs
        raise TorBoxConnectionError("secret rejected")

    monkeypatch.setattr(setup_api, "_effective_torbox_api_key", fake_api_key)
    monkeypatch.setattr(setup_api, "check_torbox_connection", fake_check_torbox_connection)

    response = await _post_torbox_test()

    assert response.status_code == httpx.codes.OK
    assert response.json() == {
        "ok": False,
        "message": "TorBox connection failed.",
    }
    assert "secret" not in response.text


async def _post_torbox_test(payload: dict[str, str] | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post("/api/setup/test/torbox", json=payload or {})
