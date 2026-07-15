"""Tests for search stream add/remove API routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, ClassVar

import httpx
import pytest

from app.api import search as search_api
from app.core.config import get_settings
from app.db.dependencies import get_optional_db_session
from app.db.repositories.stream_selection import StreamSelectionRecord, StreamSelectionWrite
from app.main import create_app
from app.providers.aiostreams.client import AioStreamsClient
from app.providers.torbox.client import TorBoxAPIError, TorBoxClient
from app.search.auto_sync import AutoSyncOutcome
from tests.conftest import override_auth


class FakeSession:
    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


def test_torbox_action_errors_are_redacted() -> None:
    message = search_api._safe_action_message(TorBoxAPIError("provider detail: account=123"))

    assert message == "TorBox operation failed."


class FakeStreamSelectionRepository:
    records: ClassVar[dict[str, StreamSelectionRecord]] = {}

    def __init__(self, session: object) -> None:
        _ = session

    async def selected_keys(self, stream_keys: list[str]) -> set[str]:
        return {stream_key for stream_key in stream_keys if stream_key in self.records}

    async def get(self, stream_key: str) -> StreamSelectionRecord | None:
        return self.records.get(stream_key)

    async def list_selected(self) -> tuple[StreamSelectionRecord, ...]:
        return tuple(self.records.values())

    async def upsert(self, write: StreamSelectionWrite) -> StreamSelectionRecord:
        record = StreamSelectionRecord(
            stream_key=write.stream_key,
            media_type=write.media_type,
            media_id=write.media_id,
            title=write.title,
            source_name=write.source_name,
            info_hash=write.info_hash,
            torbox_torrent_id=write.torbox_torrent_id,
            status=write.status,
        )
        self.records[record.stream_key] = record
        return record

    async def update_torbox_id(self, stream_key: str, torbox_torrent_id: str | None) -> None:
        record = self.records.get(stream_key)
        if record is None:
            return
        self.records[stream_key] = StreamSelectionRecord(
            stream_key=record.stream_key,
            media_type=record.media_type,
            media_id=record.media_id,
            title=record.title,
            source_name=record.source_name,
            info_hash=record.info_hash,
            torbox_torrent_id=torbox_torrent_id,
            status=record.status,
        )

    async def delete(self, stream_key: str) -> bool:
        return self.records.pop(stream_key, None) is not None


def _client_with_fake_session() -> httpx.AsyncClient:
    app = create_app()
    override_auth(app)

    async def fake_session() -> AsyncIterator[FakeSession]:
        yield FakeSession()

    app.dependency_overrides[get_optional_db_session] = fake_session
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


def _mock_hash_streams_response() -> dict[str, Any]:
    return {
        "streams": [
            {
                "name": "[TB⚡] Test Stream",
                "title": "Movie.1080p.BluRay.x264.mkv",
                "infoHash": "4fb46a63360b938999b72a73e2c19f2231f8a5c3",
                "behaviorHints": {"filename": "Movie.1080p.BluRay.x264.mkv"},
            }
        ]
    }


def _mock_url_streams_response() -> dict[str, Any]:
    return {
        "streams": [
            {
                "name": "Direct Stream",
                "title": "Movie.1080p.WEB-DL.x264.mkv",
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
async def test_add_stream_adds_torrent_and_marks_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeStreamSelectionRepository.records = {}
    monkeypatch.setattr(search_api, "StreamSelectionRepository", FakeStreamSelectionRepository)
    monkeypatch.setenv("STRMLINE_AIOSTREAMS_BASE_URL", "http://aiostreams.test/manifest.json")
    monkeypatch.setenv("STRMLINE_TORBOX_API_KEY", "test_torbox_key")
    get_settings.cache_clear()

    async def mock_aiostreams_get_json(self: object, url: str) -> dict[str, Any]:
        _ = (self, url)
        return _mock_hash_streams_response()

    seen_create: dict[str, object] = {}

    async def mock_create_torrent(
        self: object,
        *,
        magnet: str,
        name: str | None = None,
        add_only_if_cached: bool = True,
    ) -> dict[str, Any]:
        _ = self
        seen_create.update({"magnet": magnet, "name": name, "cached": add_only_if_cached})
        return {"torrent_id": 777}

    monkeypatch.setattr(AioStreamsClient, "_get_json", mock_aiostreams_get_json)
    monkeypatch.setattr(TorBoxClient, "create_torrent", mock_create_torrent)
    monkeypatch.setattr(search_api, "auto_sync_after_stream_add", mock_sync_success)

    async with _client_with_fake_session() as client:
        stream = (
            await client.post(
                "/api/search/streams",
                json={"media_type": "movie", "imdb_id": "tt1234567"},
            )
        ).json()["streams"][0]
        add_response = await client.post(
            "/api/search/streams/add",
            json={
                "media_type": "movie",
                "imdb_id": "tt1234567",
                "stream_key": stream["stream_key"],
            },
        )

    payload = add_response.json()
    assert payload["torbox_torrent_id"] == "777"
    assert payload["auto_sync_status"] == "success"
    assert payload["auto_sync_run_id"] == 12
    assert seen_create["cached"] is True
    assert str(seen_create["magnet"]).startswith("magnet:?xt=urn:btih:")


@pytest.mark.asyncio
async def test_add_stream_triggers_aiostreams_torbox_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeStreamSelectionRepository.records = {}
    monkeypatch.setattr(search_api, "StreamSelectionRepository", FakeStreamSelectionRepository)
    monkeypatch.setenv("STRMLINE_AIOSTREAMS_BASE_URL", "http://aiostreams.test/manifest.json")
    monkeypatch.setenv("STRMLINE_TORBOX_API_KEY", "test_torbox_key")
    get_settings.cache_clear()

    async def mock_aiostreams_get_json(self: object, url: str) -> dict[str, Any]:
        _ = (self, url)
        return _mock_url_streams_response()

    triggered_urls: list[str] = []

    async def mock_trigger_stream_url(self: object, url: str) -> object:
        _ = self
        triggered_urls.append(url)
        return object()

    list_calls = 0

    async def mock_list_downloads(
        self: object,
        kind: object,
        *,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        nonlocal list_calls
        _ = (self, kind, limit)
        list_calls += 1
        if list_calls == 1:
            return []
        return [
            {
                "id": 888,
                "files": [
                    {
                        "name": "Movie.1080p.WEB-DL.x264.mkv",
                        "size": 4500000000,
                    }
                ],
            }
        ]

    monkeypatch.setattr(AioStreamsClient, "_get_json", mock_aiostreams_get_json)
    monkeypatch.setattr(AioStreamsClient, "trigger_stream_url", mock_trigger_stream_url)
    monkeypatch.setattr(TorBoxClient, "list_downloads", mock_list_downloads)
    monkeypatch.setattr(search_api, "auto_sync_after_stream_add", mock_sync_success)

    async with _client_with_fake_session() as client:
        stream = (
            await client.post(
                "/api/search/streams",
                json={"media_type": "movie", "imdb_id": "tt1234567"},
            )
        ).json()["streams"][0]
        add_response = await client.post(
            "/api/search/streams/add",
            json={
                "media_type": "movie",
                "imdb_id": "tt1234567",
                "stream_key": stream["stream_key"],
            },
        )

    payload = add_response.json()
    assert payload["torbox_torrent_id"] == "888"
    assert payload["auto_sync_status"] == "success"
    assert triggered_urls == ["https://example.invalid/play"]


@pytest.mark.asyncio
async def test_add_stream_keeps_selection_when_auto_sync_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeStreamSelectionRepository.records = {}
    monkeypatch.setattr(search_api, "StreamSelectionRepository", FakeStreamSelectionRepository)
    monkeypatch.setenv("STRMLINE_AIOSTREAMS_BASE_URL", "http://aiostreams.test/manifest.json")
    monkeypatch.setenv("STRMLINE_TORBOX_API_KEY", "test_torbox_key")
    get_settings.cache_clear()

    async def mock_aiostreams_get_json(self: object, url: str) -> dict[str, Any]:
        _ = (self, url)
        return _mock_hash_streams_response()

    async def mock_create_torrent(
        self: object,
        *,
        magnet: str,
        name: str | None = None,
        add_only_if_cached: bool = True,
    ) -> dict[str, Any]:
        _ = (self, magnet, name, add_only_if_cached)
        return {"torrent_id": 777}

    async def mock_sync_failure(*args: object, **kwargs: object) -> AutoSyncOutcome:
        _ = (args, kwargs)
        return AutoSyncOutcome(
            status="failed",
            sync_run_id=None,
            message="Added. Automatic sync failed: Library root is not configured.",
        )

    monkeypatch.setattr(AioStreamsClient, "_get_json", mock_aiostreams_get_json)
    monkeypatch.setattr(TorBoxClient, "create_torrent", mock_create_torrent)
    monkeypatch.setattr(search_api, "auto_sync_after_stream_add", mock_sync_failure)

    async with _client_with_fake_session() as client:
        stream = (
            await client.post(
                "/api/search/streams",
                json={"media_type": "movie", "imdb_id": "tt1234567"},
            )
        ).json()["streams"][0]
        response = await client.post(
            "/api/search/streams/add",
            json={
                "media_type": "movie",
                "imdb_id": "tt1234567",
                "stream_key": stream["stream_key"],
            },
        )

    payload = response.json()
    assert payload["ok"] is True
    assert payload["selected"] is True
    assert payload["auto_sync_status"] == "failed"
    assert payload["auto_sync_run_id"] is None
    assert "Automatic sync failed" in payload["message"]


@pytest.mark.asyncio
async def test_remove_stream_deletes_torbox_item_and_local_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream_key = "selected-stream-key"
    FakeStreamSelectionRepository.records = {
        stream_key: StreamSelectionRecord(
            stream_key=stream_key,
            media_type="movie",
            media_id="tt1234567",
            title="Selected Movie",
            source_name="[TB⚡] Test",
            info_hash="4fb46a63360b938999b72a73e2c19f2231f8a5c3",
            torbox_torrent_id="777",
            status="selected",
        )
    }
    monkeypatch.setattr(search_api, "StreamSelectionRepository", FakeStreamSelectionRepository)
    monkeypatch.setenv("STRMLINE_TORBOX_API_KEY", "test_torbox_key")
    get_settings.cache_clear()

    seen_delete: list[str] = []

    async def mock_delete_torrent(self: object, torrent_id: str) -> None:
        _ = self
        seen_delete.append(torrent_id)

    monkeypatch.setattr(TorBoxClient, "delete_torrent", mock_delete_torrent)

    async with _client_with_fake_session() as client:
        response = await client.post(
            "/api/search/streams/remove",
            json={"stream_key": stream_key},
        )

    assert response.json()["selected"] is False
    assert seen_delete == ["777"]
    assert stream_key not in FakeStreamSelectionRepository.records


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_code", "expected_message"),
    [
        (
            "ITEM_NOT_FOUND",
            "Removed from Strmline; torrent was already absent from TorBox.",
        ),
        (
            "AUTH_ERROR",
            "Removed from Strmline, but TorBox removal could not be confirmed.",
        ),
    ],
)
async def test_remove_stream_is_not_blocked_by_torbox_failure(
    monkeypatch: pytest.MonkeyPatch,
    error_code: str,
    expected_message: str,
) -> None:
    stream_key = "stale-selected-stream-key"
    FakeStreamSelectionRepository.records = {
        stream_key: StreamSelectionRecord(
            stream_key=stream_key,
            media_type="movie",
            media_id="tt1234567",
            title="Stale Selected Movie",
            source_name="[TB⚡] Test",
            info_hash="4fb46a63360b938999b72a73e2c19f2231f8a5c3",
            torbox_torrent_id="777",
            status="selected",
        )
    }
    monkeypatch.setattr(search_api, "StreamSelectionRepository", FakeStreamSelectionRepository)
    monkeypatch.setenv("STRMLINE_TORBOX_API_KEY", "test_torbox_key")
    get_settings.cache_clear()

    async def mock_delete_torrent(self: object, torrent_id: str) -> None:
        _ = (self, torrent_id)
        raise TorBoxAPIError("provider detail", error_code=error_code)

    monkeypatch.setattr(TorBoxClient, "delete_torrent", mock_delete_torrent)

    async with _client_with_fake_session() as client:
        response = await client.post(
            "/api/search/streams/remove",
            json={"stream_key": stream_key},
        )

    payload = response.json()
    assert payload["ok"] is True
    assert payload["selected"] is False
    assert payload["message"] == expected_message
    assert stream_key not in FakeStreamSelectionRepository.records


async def mock_sync_success(*args: object, **kwargs: object) -> AutoSyncOutcome:
    _ = (args, kwargs)
    return AutoSyncOutcome(
        status="success",
        sync_run_id=12,
        message="Added. Synced library: 1 written, 0 skipped.",
    )
