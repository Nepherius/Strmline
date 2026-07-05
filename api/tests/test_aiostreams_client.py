import httpx
import pytest

from app.providers.aiostreams.client import (
    AioStreamsClient,
    AioStreamsClientError,
)


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
