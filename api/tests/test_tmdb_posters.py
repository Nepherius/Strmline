from __future__ import annotations

import httpx
import pytest

from app.providers.tmdb.posters import TmdbPosterClient, TmdbPosterError


@pytest.mark.asyncio
async def test_tmdb_poster_client_fetches_supported_image() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "image/jpeg"},
            content=b"\xff\xd8\xffposter-data",
            request=request,
        )
    )
    client = TmdbPosterClient(timeout_seconds=1, transport=transport)

    poster = await client.fetch("/poster.jpg")

    assert poster.content == b"\xff\xd8\xffposter-data"
    assert poster.suffix == ".jpg"


@pytest.mark.asyncio
async def test_tmdb_poster_client_rejects_invalid_paths_and_responses() -> None:
    client = TmdbPosterClient(timeout_seconds=1)
    with pytest.raises(TmdbPosterError, match="path is invalid"):
        _ = await client.fetch("https://example.test/poster.jpg")

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            content=b"not an image",
            request=request,
        )
    )
    invalid_content_client = TmdbPosterClient(timeout_seconds=1, transport=transport)
    with pytest.raises(TmdbPosterError, match="supported image"):
        _ = await invalid_content_client.fetch("/poster")
