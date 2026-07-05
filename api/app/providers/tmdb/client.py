from __future__ import annotations

from typing import Any, cast

import httpx

HTTP_UNAUTHORIZED = 401


class TmdbClientError(RuntimeError):
    """Raised when a safe TMDB API request fails."""


class TmdbClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def get_json(
        self,
        endpoint: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout_seconds,
            transport=self._transport,
        ) as client:
            return await self._get_json(client, endpoint, params=params or {})

    async def _get_json(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        *,
        params: dict[str, str],
    ) -> dict[str, Any]:
        response = await _safe_get(
            client,
            endpoint,
            headers={"Authorization": f"Bearer {self._api_key}"},
            params=params,
        )
        if response.status_code == HTTP_UNAUTHORIZED:
            response = await _safe_get(
                client,
                endpoint,
                params={**params, "api_key": self._api_key},
            )
        if response.is_error:
            raise TmdbClientError("TMDB request failed.")
        try:
            payload = response.json()
        except ValueError as error:
            raise TmdbClientError("TMDB response was not JSON.") from error
        if not isinstance(payload, dict):
            raise TmdbClientError("TMDB response was not an object.")
        return cast(dict[str, Any], payload)


async def _safe_get(
    client: httpx.AsyncClient,
    endpoint: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
) -> httpx.Response:
    try:
        return await client.get(endpoint, headers=headers, params=params)
    except httpx.HTTPError as error:
        raise TmdbClientError("TMDB request failed.") from error
