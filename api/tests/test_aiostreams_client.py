import httpx
import pytest

from app.providers.aiostreams.client import (
    AioStreamsClient,
    AioStreamsClientError,
)

USER_UUID = "12345678-1234-5678-1234-567812345678"


@pytest.mark.asyncio
async def test_aiostreams_client_reads_manifest() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/addon/manifest.json"
        return httpx.Response(
            200,
            json={
                "id": "community.aiostreams",
                "name": "AIOStreams",
                "version": "1.0.0",
                "resources": ["stream"],
                "types": ["movie", "series"],
            },
        )

    manifest = await AioStreamsClient(
        base_url="https://example.test/addon",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    ).manifest()

    assert manifest.name == "AIOStreams"
    assert manifest.resources == ("stream",)
    assert manifest.types == ("movie", "series")


@pytest.mark.asyncio
async def test_aiostreams_client_reads_streams() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/addon/stream/movie/tt123.json"
        return httpx.Response(
            200,
            json={
                "streams": [
                    {
                        "name": "1080p",
                        "title": "Example release",
                        "url": "https://stream.example/video.mkv",
                        "behaviorHints": {"filename": "video.mkv"},
                    },
                    {
                        "name": "Torrent",
                        "infoHash": "abc123",
                        "fileIdx": 2,
                    },
                    "ignored",
                ]
            },
        )

    streams = await AioStreamsClient(
        base_url="https://example.test/addon/manifest.json",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    ).streams(media_type="movie", media_id="tt123")

    assert len(streams) == 2
    assert streams[0].playable is True
    assert streams[0].url == "https://stream.example/video.mkv"
    assert streams[1].info_hash == "abc123"
    assert streams[1].file_idx == 2


@pytest.mark.asyncio
async def test_aiostreams_client_prefers_structured_search_api() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/search"
        assert dict(request.url.params) == {
            "type": "movie",
            "id": "tt123",
            "format": "true",
        }
        assert request.headers["authorization"].startswith("Basic ")
        return httpx.Response(
            200,
            json={
                "success": True,
                "detail": None,
                "error": None,
                "data": {
                    "filtered": 0,
                    "statistics": [],
                    "errors": [],
                    "results": [
                        {
                            "name": "Instant TB",
                            "description": "Cached TorBox result",
                            "infoHash": "ab" * 20,
                            "fileIdx": 2,
                            "filename": "Example.Movie.2160p.mkv",
                            "size": 12_345,
                            "seeders": 42,
                            "cached": True,
                            "service": "torbox",
                            "addon": "TorBox Search",
                            "url": "https://stream.example/action",
                        }
                    ],
                },
            },
        )

    streams = await AioStreamsClient(
        base_url=(f"https://example.test/stremio/{USER_UUID}/encrypted-password/manifest.json"),
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    ).streams(media_type="movie", media_id="tt123")

    assert len(streams) == 1
    assert streams[0].info_hash == "ab" * 20
    assert streams[0].file_idx == 2
    assert streams[0].behavior_hints == {
        "filename": "Example.Movie.2160p.mkv",
        "seeders": 42,
        "videoSize": 12_345,
    }
    assert streams[0].raw["cached"] is True


@pytest.mark.asyncio
async def test_aiostreams_client_falls_back_when_search_api_is_unavailable() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/api/v1/search":
            return httpx.Response(404)
        assert request.url.path == (
            f"/stremio/{USER_UUID}/encrypted-password/stream/movie/tt123.json"
        )
        return httpx.Response(
            200,
            json={"streams": [{"name": "Torrent", "infoHash": "cd" * 20}]},
        )

    streams = await AioStreamsClient(
        base_url=(f"https://example.test/stremio/{USER_UUID}/encrypted-password/manifest.json"),
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    ).streams(media_type="movie", media_id="tt123")

    assert streams[0].info_hash == "cd" * 20
    assert paths == [
        "/api/v1/search",
        f"/stremio/{USER_UUID}/encrypted-password/stream/movie/tt123.json",
    ]


@pytest.mark.asyncio
async def test_aiostreams_client_reuses_recent_stream_results() -> None:
    requests = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(
            200,
            json={"streams": [{"name": "Torrent", "infoHash": "abc123"}]},
        )

    client = AioStreamsClient(
        base_url="https://cache.example/addon",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )

    first = await client.streams(media_type="movie", media_id="tt123")
    second = await client.streams(media_type="movie", media_id="tt123")

    assert second is first
    assert requests == 1


@pytest.mark.asyncio
async def test_aiostreams_client_rejects_invalid_stream_payload() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"streams": {}})

    with pytest.raises(AioStreamsClientError, match="streams"):
        _ = await AioStreamsClient(
            base_url="https://example.test/addon",
            timeout_seconds=5,
            transport=httpx.MockTransport(handler),
        ).streams(media_type="movie", media_id="tt123")


@pytest.mark.asyncio
async def test_aiostreams_client_error_message_is_safe() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"secret": "should-not-surface"})

    with pytest.raises(AioStreamsClientError) as error:
        _ = await AioStreamsClient(
            base_url="https://example.test/addon",
            timeout_seconds=5,
            transport=httpx.MockTransport(handler),
        ).manifest()

    assert "should-not-surface" not in str(error.value)


@pytest.mark.asyncio
async def test_aiostreams_client_triggers_stream_url_without_following_redirects() -> None:
    seen_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers["range"] = request.headers["range"]
        return httpx.Response(302, headers={"location": "https://cdn.example/video.mkv"})

    result = await AioStreamsClient(
        base_url="https://example.test/addon",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    ).trigger_stream_url("https://streams.example/add/123")

    assert result.status_code == 302
    assert result.redirected is True
    assert seen_headers == {"range": "bytes=0-0"}


@pytest.mark.asyncio
async def test_aiostreams_client_rejects_private_trigger_url() -> None:
    with pytest.raises(AioStreamsClientError, match="not allowed"):
        _ = await AioStreamsClient(
            base_url="https://example.test/addon",
            timeout_seconds=5,
        ).trigger_stream_url("http://127.0.0.1/internal")
