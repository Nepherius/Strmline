"""Tests for search API routes using environment settings and mocks."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.core.config import get_settings
from app.main import create_app
from app.providers.aiostreams.client import AioStreamsClient
from app.providers.tmdb.client import TmdbClient
from tests.conftest import override_auth


@pytest.fixture
def app_client() -> httpx.AsyncClient:
    app = create_app()
    override_auth(app)
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


def _mock_tmdb_search_response() -> dict[str, Any]:
    return {
        "results": [
            {
                "id": 12345,
                "media_type": "movie",
                "title": "Test Movie",
                "release_date": "2026-01-01",
                "overview": "A test movie",
                "poster_path": "/test.jpg",
            },
            {
                "id": 67890,
                "media_type": "tv",
                "name": "Test Show",
                "first_air_date": "2025-09-01",
                "overview": "A test show",
                "poster_path": "/show.jpg",
            },
        ]
    }


def _mock_tmdb_external_ids_response() -> dict[str, Any]:
    return {
        "imdb_id": "tt1234567",
    }


def _mock_aiostreams_streams_response() -> dict[str, Any]:
    return {
        "streams": [
            {
                "name": "[TB⚡] Test Stream",
                "title": "Movie.1080p.BluRay.x264.mkv\n4.5 GB",
                "description": "Seeders: 10",
                "infoHash": "4fb46a63360b938999b72a73e2c19f2231f8a5c3",
                "behaviorHints": {
                    "filename": "Movie.1080p.BluRay.x264.mkv",
                    "videoSize": 4500000000,
                    "seeders": 10,
                },
            }
        ]
    }


def _mock_aiostreams_direct_torbox_streams_response() -> dict[str, Any]:
    return {
        "streams": [
            {
                "name": "Direct Stream",
                "title": "Movie.1080p.WEB-DL.x264.mkv\n4.5 GB",
                "description": "Instant TB",
                "url": "https://example.invalid/play",
                "behaviorHints": {
                    "filename": "Movie.1080p.WEB-DL.x264.mkv",
                    "videoSize": 4500000000,
                },
            }
        ]
    }


@pytest.mark.asyncio
async def test_search_titles_not_configured(
    app_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STRMLINE_TMDB_API_KEY", raising=False)
    get_settings.cache_clear()

    response = await app_client.post(
        "/api/search/titles",
        json={"query": "Test"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert "TMDB is not configured" in payload["message"]


@pytest.mark.asyncio
async def test_search_titles_success(
    app_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRMLINE_TMDB_API_KEY", "test_tmdb_key")
    get_settings.cache_clear()

    async def mock_get_json(
        self: object,
        endpoint: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        assert endpoint == "/search/multi"
        assert params == {"query": "Test", "include_adult": "false"}
        _ = self
        return _mock_tmdb_search_response()

    monkeypatch.setattr(TmdbClient, "get_json", mock_get_json)

    response = await app_client.post(
        "/api/search/titles",
        json={"query": "Test"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert len(payload["results"]) == 2
    assert payload["results"][0]["title"] == "Test Movie"
    assert payload["results"][0]["tmdb_id"] == 12345
    assert payload["results"][0]["media_type"] == "movie"
    assert payload["results"][0]["poster_url"] == "https://image.tmdb.org/t/p/w342/test.jpg"
    assert payload["results"][0]["poster_path"] == "/test.jpg"
    assert payload["results"][1]["title"] == "Test Show"
    assert payload["results"][1]["media_type"] == "series"


@pytest.mark.asyncio
async def test_search_titles_direct_imdb_id(
    app_client: httpx.AsyncClient,
) -> None:
    response = await app_client.post(
        "/api/search/titles",
        json={"query": "tt1234567"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert len(payload["results"]) == 1
    assert payload["results"][0]["imdb_id"] == "tt1234567"
    assert "Direct IMDB ID lookup" in payload["results"][0]["overview"]


@pytest.mark.asyncio
async def test_search_streams_not_configured(
    app_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STRMLINE_AIOSTREAMS_BASE_URL", raising=False)
    get_settings.cache_clear()

    response = await app_client.post(
        "/api/search/streams",
        json={"media_type": "movie", "imdb_id": "tt1234567"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert "AIOStreams is not configured" in payload["message"]


@pytest.mark.asyncio
async def test_search_streams_preserves_aiostreams_name_marker(
    app_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRMLINE_AIOSTREAMS_BASE_URL", "http://aiostreams.test/manifest.json")
    get_settings.cache_clear()

    async def mock_aiostreams_get_json(self: object, url: str) -> dict[str, Any]:
        _ = (self, url)
        return _mock_aiostreams_streams_response()

    monkeypatch.setattr(AioStreamsClient, "_get_json", mock_aiostreams_get_json)

    response = await app_client.post(
        "/api/search/streams",
        json={"media_type": "movie", "imdb_id": "tt1234567"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["stream_count"] == 1
    assert payload["streams"][0]["title"] == "[TB⚡] Test Stream - Movie.1080p.BluRay.x264.mkv"
    assert len(payload["streams"][0]["stream_key"]) == 32
    assert payload["streams"][0]["cached"] is None
    assert payload["streams"][0]["addable"] is True
    assert payload["streams"][0]["selected"] is False
    assert payload["streams"][0]["provider_label"] is None
    assert payload["streams"][0]["parsed"]["quality"] == "1080p"
    assert payload["streams"][0]["parsed"]["size_label"] == "4.2 GB"


@pytest.mark.asyncio
async def test_search_streams_keeps_action_label_without_cache_check(
    app_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRMLINE_AIOSTREAMS_BASE_URL", "http://aiostreams.test/manifest.json")
    get_settings.cache_clear()

    async def mock_aiostreams_get_json(self: object, url: str) -> dict[str, Any]:
        _ = (self, url)
        return _mock_aiostreams_direct_torbox_streams_response()

    monkeypatch.setattr(AioStreamsClient, "_get_json", mock_aiostreams_get_json)

    response = await app_client.post(
        "/api/search/streams",
        json={"media_type": "movie", "imdb_id": "tt1234567"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["streams"][0]["title"] == "Direct Stream - Movie.1080p.WEB-DL.x264.mkv"
    assert payload["streams"][0]["cached"] is None
    assert payload["streams"][0]["has_url"] is True
    assert payload["streams"][0]["has_info_hash"] is False
    assert payload["streams"][0]["addable"] is True
    assert payload["streams"][0]["provider_label"] == "Instant TB"


@pytest.mark.asyncio
async def test_search_streams_for_series_uses_broad_series_lookup(
    app_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRMLINE_AIOSTREAMS_BASE_URL", "http://aiostreams.test/manifest.json")
    get_settings.cache_clear()

    async def mock_aiostreams_get_json(self: object, url: str) -> dict[str, Any]:
        _ = self
        assert url == "http://aiostreams.test/stream/series/tt1234567.json"
        return _mock_aiostreams_direct_torbox_streams_response()

    monkeypatch.setattr(AioStreamsClient, "_get_json", mock_aiostreams_get_json)

    response = await app_client.post(
        "/api/search/streams",
        json={"media_type": "series", "imdb_id": "tt1234567"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["stream_count"] == 1


@pytest.mark.asyncio
async def test_search_streams_resolves_tmdb_id(
    app_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRMLINE_TMDB_API_KEY", "test_tmdb_key")
    monkeypatch.setenv("STRMLINE_AIOSTREAMS_BASE_URL", "http://aiostreams.test/manifest.json")
    get_settings.cache_clear()

    async def mock_tmdb_get_json(
        self: object,
        endpoint: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        _ = (self, endpoint, params)
        return _mock_tmdb_external_ids_response()

    monkeypatch.setattr(TmdbClient, "get_json", mock_tmdb_get_json)

    async def mock_aiostreams_get_json(self: object, url: str) -> dict[str, Any]:
        _ = (self, url)
        return _mock_aiostreams_streams_response()

    monkeypatch.setattr(AioStreamsClient, "_get_json", mock_aiostreams_get_json)

    response = await app_client.post(
        "/api/search/streams",
        json={"media_type": "movie", "tmdb_id": 12345},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["stream_count"] == 1
    assert payload["streams"][0]["cached"] is None
