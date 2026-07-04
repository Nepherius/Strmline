import httpx
import pytest

from app.providers.tmdb.connection import TmdbConnectionError, check_tmdb_connection


@pytest.mark.asyncio
async def test_tmdb_connection_uses_bearer_token_first() -> None:
    seen_headers: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(request.headers.get("authorization"))
        return httpx.Response(200, json={"images": {}})

    await check_tmdb_connection(
        api_key="tmdb-secret",
        base_url="https://api.themoviedb.org/3",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )

    assert seen_headers == ["Bearer tmdb-secret"]


@pytest.mark.asyncio
async def test_tmdb_connection_falls_back_to_v3_api_key_query_param() -> None:
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        if len(seen_urls) == 1:
            return httpx.Response(401, json={"status_message": "Invalid API key"})
        return httpx.Response(200, json={"images": {}})

    await check_tmdb_connection(
        api_key="tmdb-secret",
        base_url="https://api.themoviedb.org/3",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )

    assert seen_urls == [
        "https://api.themoviedb.org/3/configuration",
        "https://api.themoviedb.org/3/configuration?api_key=tmdb-secret",
    ]


@pytest.mark.asyncio
async def test_tmdb_connection_error_does_not_expose_api_key() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"status_message": "Invalid API key"})

    with pytest.raises(TmdbConnectionError) as error:
        await check_tmdb_connection(
            api_key="tmdb-secret",
            base_url="https://api.themoviedb.org/3",
            timeout_seconds=5,
            transport=httpx.MockTransport(handler),
        )

    assert "tmdb-secret" not in str(error.value)
