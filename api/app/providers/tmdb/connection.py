from __future__ import annotations

import httpx

from app.providers.tmdb.client import uses_bearer_token


class TmdbConnectionError(RuntimeError):
    """Raised when a safe TMDB connection test fails."""


async def check_tmdb_connection(
    *,
    api_key: str,
    base_url: str,
    timeout_seconds: float,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    async with httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        timeout=timeout_seconds,
        transport=transport,
    ) as client:
        if uses_bearer_token(api_key):
            if await _request_succeeded(client, headers={"Authorization": f"Bearer {api_key}"}):
                return
            if await _request_succeeded(client, params={"api_key": api_key}):
                return
        elif await _request_succeeded(client, params={"api_key": api_key}):
            return
    raise TmdbConnectionError("TMDB connection failed.")


async def _request_succeeded(
    client: httpx.AsyncClient,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
) -> bool:
    try:
        response = await client.get("/configuration", headers=headers, params=params)
    except httpx.HTTPError as error:
        raise TmdbConnectionError("TMDB connection failed.") from error
    if response.is_error:
        return False
    try:
        payload = response.json()
    except ValueError as error:
        raise TmdbConnectionError("TMDB response was not JSON.") from error
    return isinstance(payload, dict)
