import httpx
import pytest

from app.api import aiostreams as aiostreams_api
from app.core.config import get_settings
from app.db.dependencies import get_optional_db_session
from app.main import create_app
from app.providers.aiostreams.client import (
    AioStreamsClientError,
    AioStreamsManifest,
    AioStreamsStream,
)
from tests.conftest import override_auth


@pytest.mark.asyncio
async def test_aiostreams_test_route_reports_missing_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STRMLINE_AIOSTREAMS_BASE_URL", raising=False)
    get_settings.cache_clear()

    try:
        response = await _post_test({})
    finally:
        get_settings.cache_clear()

    assert response.status_code == httpx.codes.OK
    assert response.json() == {
        "ok": False,
        "message": "AIOStreams URL is not configured.",
        "addon_name": None,
        "addon_version": None,
        "resources": [],
        "types": [],
        "stream_count": None,
        "streams": [],
    }


@pytest.mark.asyncio
async def test_aiostreams_test_route_returns_sanitized_streams(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(aiostreams_api, "AioStreamsClient", FakeAioStreamsClient)
    response = await _post_test(
        {
            "base_url": "https://example.test/addon",
            "media_type": "movie",
            "media_id": "tt123",
        }
    )

    assert response.status_code == httpx.codes.OK
    payload = response.json()
    assert payload["ok"] is True
    assert payload["addon_name"] == "AIOStreams"
    assert payload["resources"] == ["stream"]
    assert payload["types"] == ["movie", "series"]
    assert payload["stream_count"] == 1
    assert payload["streams"] == [
        {
            "name": "1080p",
            "title": "Example release",
            "description": None,
            "has_url": True,
            "has_info_hash": True,
            "file_idx": 1,
            "behavior_hints": {
                "filename": "video.mkv",
                "videoSize": 1073741824,
            },
        }
    ]
    assert "https://stream.example/video.mkv" not in response.text
    assert "abc123" not in response.text
    assert "unsafe-hash" not in response.text


@pytest.mark.asyncio
async def test_aiostreams_test_route_uses_saved_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(aiostreams_api, "AioStreamsClient", SavedUrlAioStreamsClient)
    monkeypatch.setattr(aiostreams_api, "AppSettingsRepository", FakeSettingsRepository)

    app = create_app()
    override_auth(app)
    app.dependency_overrides[get_optional_db_session] = fake_optional_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/providers/aiostreams/test", json={})

    assert response.status_code == httpx.codes.OK
    assert response.json()["ok"] is True


@pytest.mark.asyncio
async def test_aiostreams_test_route_returns_safe_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(aiostreams_api, "AioStreamsClient", FailingAioStreamsClient)
    response = await _post_test({"base_url": "https://example.test/addon"})

    assert response.status_code == httpx.codes.OK
    assert response.json()["ok"] is False
    assert response.json()["message"] == "AIOStreams connection failed."


async def _post_test(payload: dict[str, str]) -> httpx.Response:
    app = create_app()
    override_auth(app)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post("/api/providers/aiostreams/test", json=payload)


class FakeAioStreamsClient:
    def __init__(self, *, base_url: str, timeout_seconds: float) -> None:
        assert base_url == "https://example.test/addon"
        assert timeout_seconds > 0

    async def manifest(self) -> AioStreamsManifest:
        return AioStreamsManifest(
            id="community.aiostreams",
            name="AIOStreams",
            version="1.0.0",
            resources=("stream",),
            types=("movie", "series"),
        )

    async def streams(self, *, media_type: str, media_id: str) -> tuple[AioStreamsStream, ...]:
        assert media_type == "movie"
        assert media_id == "tt123"
        return (
            AioStreamsStream(
                name="1080p",
                title="Example release",
                description=None,
                url="https://stream.example/video.mkv",
                info_hash="abc123",
                file_idx=1,
                behavior_hints={
                    "filename": "video.mkv",
                    "videoSize": 1073741824,
                    "videoHash": "unsafe-hash",
                },
                raw={},
            ),
        )


class FailingAioStreamsClient:
    def __init__(self, *, base_url: str, timeout_seconds: float) -> None:
        _ = base_url
        _ = timeout_seconds

    async def manifest(self) -> AioStreamsManifest:
        raise AioStreamsClientError("secret detail")


class SavedUrlAioStreamsClient(FakeAioStreamsClient):
    def __init__(self, *, base_url: str, timeout_seconds: float) -> None:
        assert base_url == "https://saved-aio.example/manifest.json"
        assert timeout_seconds > 0


class FakeSettingsRepository:
    def __init__(self, session: object, settings: object) -> None:
        _ = session
        _ = settings

    async def aiostreams_base_url_value(self) -> str:
        return "https://saved-aio.example/manifest.json"


async def fake_optional_session() -> object:
    yield object()
