import json

import httpx
import pytest

from app.providers.torbox.client import TorBoxAPIError, TorBoxClient
from app.providers.torbox.files import TorBoxFile


@pytest.mark.asyncio
async def test_torbox_client_sends_auth_and_user_agent_headers() -> None:
    seen_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers["authorization"] = request.headers["authorization"]
        seen_headers["user-agent"] = request.headers["user-agent"]
        return httpx.Response(200, json={"data": [{"id": 1}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = TorBoxClient(api_key="secret-token", http_client=http_client)

        payload = await client.get_json("/torrents/mylist")

    assert payload == {"data": [{"id": 1}]}
    assert seen_headers == {
        "authorization": "Bearer secret-token",
        "user-agent": "Strmline/0.1.0",
    }


@pytest.mark.asyncio
async def test_torbox_client_joins_base_url_and_relative_paths() -> None:
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = TorBoxClient(
            api_key="secret-token",
            base_url="https://api.example.test/v1/api",
            http_client=http_client,
        )

        _ = await client.get_json("torrents/mylist", params={"page": 1})

    assert seen_urls == ["https://api.example.test/v1/api/torrents/mylist?page=1"]


@pytest.mark.asyncio
async def test_torbox_client_error_does_not_expose_api_key() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "upstream failed"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = TorBoxClient(api_key="secret-token", http_client=http_client)

        with pytest.raises(TorBoxAPIError) as error:
            _ = await client.get_json("/torrents/mylist")

    assert "500" in str(error.value)
    assert "secret-token" not in str(error.value)


@pytest.mark.asyncio
async def test_torbox_client_error_includes_safe_api_detail() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "success": False,
                "error": "BAD_TOKEN",
                "detail": "Your token is invalid or has expired.",
                "data": None,
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = TorBoxClient(api_key="secret-token", http_client=http_client)

        with pytest.raises(TorBoxAPIError) as error:
            _ = await client.get_json("/torrents/mylist")

    assert "BAD_TOKEN" in str(error.value)
    assert "invalid" in str(error.value)
    assert error.value.error_code == "BAD_TOKEN"
    assert "secret-token" not in str(error.value)


@pytest.mark.asyncio
async def test_torbox_client_rejects_failed_standard_response() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": False,
                "error": "UNKNOWN_ERROR",
                "detail": "Something went wrong.",
                "data": None,
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = TorBoxClient(api_key="secret-token", http_client=http_client)

        with pytest.raises(TorBoxAPIError, match="Something went wrong"):
            _ = await client.get_json("/torrents/mylist")


@pytest.mark.asyncio
async def test_torbox_client_can_be_used_as_context_manager() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    client = TorBoxClient(api_key="secret-token", transport=transport)

    async with client as torbox:
        payload = await torbox.get_json("/torrents/mylist")

    assert payload == {"ok": True}


@pytest.mark.asyncio
async def test_torbox_client_lists_all_download_pages() -> None:
    seen_offsets: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_offsets.append(request.url.params["offset"])
        if request.url.params["offset"] == "0":
            return httpx.Response(200, json={"data": [{"id": 1}, {"id": 2}]})
        return httpx.Response(200, json={"data": [{"id": 3}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = TorBoxClient(api_key="test-token", http_client=http_client)

        downloads = await client.list_downloads("torrents", limit=2)

    assert seen_offsets == ["0", "2"]
    assert downloads == [{"id": 1}, {"id": 2}, {"id": 3}]


@pytest.mark.asyncio
async def test_torbox_client_creates_torrent_with_cached_only_form() -> None:
    seen_request: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_request["method"] = request.method
        seen_request["url"] = str(request.url)
        seen_request["content_type"] = request.headers["content-type"]
        seen_request["body"] = request.content.decode()
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {"torrent_id": 42, "hash": "abc"},
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = TorBoxClient(api_key="secret-token", http_client=http_client)

        data = await client.create_torrent(
            magnet="magnet:?xt=urn:btih:abc",
            name="Test Movie",
            add_only_if_cached=True,
        )

    assert data == {"torrent_id": 42, "hash": "abc"}
    assert seen_request["method"] == "POST"
    assert seen_request["url"] == "https://api.torbox.app/v1/api/torrents/createtorrent"
    assert "multipart/form-data" in seen_request["content_type"]
    assert 'name="magnet"' in seen_request["body"]
    assert "magnet:?xt=urn:btih:abc" in seen_request["body"]
    assert 'name="add_only_if_cached"' in seen_request["body"]
    assert "true" in seen_request["body"]
    assert "secret-token" not in seen_request["body"]


@pytest.mark.asyncio
async def test_torbox_client_deletes_torrent_with_control_endpoint() -> None:
    seen_json: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_json.update(json.loads(request.content.decode()))
        return httpx.Response(200, json={"success": True, "data": None})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = TorBoxClient(api_key="secret-token", http_client=http_client)

        await client.delete_torrent("42")

    assert seen_json == {
        "torrent_id": 42,
        "operation": "delete",
        "all": False,
    }


@pytest.mark.asyncio
async def test_torbox_client_deletes_usenet_with_control_endpoint() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["json"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"success": True, "data": None})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = TorBoxClient(api_key="secret-token", http_client=http_client)

        await client.delete_download("usenet", "42")

    assert seen == {
        "url": "https://api.torbox.app/v1/api/usenet/controlusenet",
        "json": {"usenet_id": 42, "operation": "delete", "all": False},
    }


@pytest.mark.asyncio
async def test_torbox_client_deletes_webdl_with_control_endpoint() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["json"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"success": True, "data": None})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = TorBoxClient(api_key="secret-token", http_client=http_client)

        await client.delete_download("webdl", "web-42")

    assert seen == {
        "url": "https://api.torbox.app/v1/api/webdl/controlwebdownload",
        "json": {"web_id": "web-42", "operation": "delete", "all": False},
    }


@pytest.mark.asyncio
async def test_torbox_client_finds_torrent_by_hash() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": [
                    {"id": 1, "hash": "aaa"},
                    {"id": 2, "hash": "bbb", "alternative_hashes": ["CCC"]},
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = TorBoxClient(api_key="secret-token", http_client=http_client)

        item = await client.find_torrent_by_hash("ccc")

    assert item == {"id": 2, "hash": "bbb", "alternative_hashes": ["CCC"]}


@pytest.mark.asyncio
async def test_torbox_client_fetches_one_download_by_id() -> None:
    seen_params: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_params.update(request.url.params)
        return httpx.Response(200, json={"success": True, "data": {"id": 42}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = TorBoxClient(api_key="secret-token", http_client=http_client)

        item = await client.get_download("torrents", "42")

    assert item == {"id": 42}
    assert seen_params == {"id": "42", "bypass_cache": "true"}


@pytest.mark.asyncio
async def test_torbox_client_requests_fresh_download_link() -> None:
    seen_params: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_params.update(request.url.params)
        return httpx.Response(
            200,
            json={"success": True, "data": "https://cdn.example.test/movie.mkv"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = TorBoxClient(api_key="secret-token", http_client=http_client)

        link = await client.request_download_link(
            TorBoxFile(
                kind="torrents",
                item_id="42",
                file_id="7",
                folder_name="Movie",
                file_name="Movie.mkv",
                path="Movie/Movie.mkv",
                mime_type="video/x-matroska",
                size=1_000,
            )
        )

    assert link == "https://cdn.example.test/movie.mkv"
    assert seen_params == {"token": "secret-token", "torrent_id": "42", "file_id": "7"}
