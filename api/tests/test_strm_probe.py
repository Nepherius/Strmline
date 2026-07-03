from pathlib import Path

import httpx
import pytest

from app.library.strm_probe import StrmProbeError, probe_strm_file


@pytest.mark.asyncio
async def test_probe_strm_file_accepts_redirect_without_following_location(tmp_path: Path) -> None:
    strm_path = tmp_path / "movie.strm"
    _ = strm_path.write_text("https://example.test/requestdl?token=secret\n", encoding="utf-8")
    seen_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers["range"] = request.headers["range"]
        return httpx.Response(302, headers={"location": "https://media.example.test/final-token"})

    transport = httpx.MockTransport(handler)

    result = await probe_strm_file(strm_path, transport=transport)

    assert result.ok is True
    assert result.redirected is True
    assert result.status_code == 302
    assert seen_headers == {"range": "bytes=0-0"}


@pytest.mark.asyncio
async def test_probe_strm_file_error_does_not_expose_url(tmp_path: Path) -> None:
    strm_path = tmp_path / "movie.strm"
    _ = strm_path.write_text("https://example.test/requestdl?token=secret\n", encoding="utf-8")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    transport = httpx.MockTransport(handler)

    with pytest.raises(StrmProbeError) as error:
        _ = await probe_strm_file(strm_path, transport=transport)

    assert "403" in str(error.value)
    assert "secret" not in str(error.value)
