from __future__ import annotations

import httpx

from app.providers.torbox.client import TorBoxAPIError, TorBoxClient


class TorBoxConnectionError(RuntimeError):
    """Raised when a safe TorBox connection test fails."""


async def check_torbox_connection(
    *,
    api_key: str,
    base_url: str,
    timeout_seconds: float,
) -> None:
    try:
        async with TorBoxClient(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
        ) as client:
            _ = await client.get_json(
                "/torrents/mylist",
                params={
                    "limit": 1,
                    "offset": 0,
                    "bypass_cache": True,
                },
            )
    except (httpx.HTTPError, TorBoxAPIError, ValueError) as error:
        raise TorBoxConnectionError("TorBox connection failed.") from error
