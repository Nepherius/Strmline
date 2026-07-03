from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx

PROBE_USER_AGENT = "Strmline/0.1.0"
SUCCESS_STATUSES = {200, 204, 206}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class StrmProbeError(RuntimeError):
    """Raised when a generated .strm URL cannot be probed safely."""


@dataclass(frozen=True, slots=True)
class StrmProbeResult:
    path: Path
    status_code: int
    redirected: bool
    ok: bool


async def probe_strm_file(
    path: Path,
    *,
    request_timeout: float = 20.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> StrmProbeResult:
    url = _read_strm_url(path)
    try:
        async with (
            httpx.AsyncClient(
                follow_redirects=False,
                timeout=request_timeout,
                transport=transport,
            ) as client,
            client.stream(
                "GET",
                url,
                headers={
                    "Range": "bytes=0-0",
                    "User-Agent": PROBE_USER_AGENT,
                },
            ) as response,
        ):
            return _probe_result(path, response.status_code)
    except httpx.HTTPError as error:
        msg = f"STRM probe failed: {error.__class__.__name__}."
        raise StrmProbeError(msg) from error


def _probe_result(path: Path, status_code: int) -> StrmProbeResult:
    redirected = status_code in REDIRECT_STATUSES
    ok = redirected or status_code in SUCCESS_STATUSES
    if not ok:
        msg = f"STRM probe failed with status {status_code}."
        raise StrmProbeError(msg)
    return StrmProbeResult(
        path=path,
        status_code=status_code,
        redirected=redirected,
        ok=ok,
    )


def _read_strm_url(path: Path) -> str:
    url = path.read_text(encoding="utf-8").strip()
    if not url:
        msg = "STRM file was empty."
        raise StrmProbeError(msg)
    return url
