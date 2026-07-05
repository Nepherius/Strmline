from __future__ import annotations

from typing import Any, cast

import httpx


class AniListClientError(RuntimeError):
    """Raised when a safe AniList GraphQL request fails."""


class AniListClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def execute(
        self,
        *,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(
            timeout=self._timeout_seconds,
            transport=self._transport,
        ) as client:
            return await self._execute(
                client,
                query=query,
                variables=variables or {},
                operation_name=operation_name,
            )

    async def _execute(
        self,
        client: httpx.AsyncClient,
        *,
        query: str,
        variables: dict[str, Any],
        operation_name: str | None,
    ) -> dict[str, Any]:
        try:
            response = await client.post(
                self._base_url,
                json={
                    "query": query,
                    "variables": variables,
                    "operationName": operation_name,
                },
            )
        except httpx.HTTPError as error:
            raise AniListClientError("AniList request failed.") from error
        if response.is_error:
            raise AniListClientError("AniList request failed.")
        try:
            payload: object = response.json()
        except ValueError as error:
            raise AniListClientError("AniList response was not JSON.") from error
        if not isinstance(payload, dict):
            raise AniListClientError("AniList response was not an object.")
        payload_data = cast(dict[str, Any], payload)
        if payload_data.get("errors"):
            raise AniListClientError("AniList returned GraphQL errors.")
        return payload_data
