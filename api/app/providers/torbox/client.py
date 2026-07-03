from __future__ import annotations

from types import TracebackType
from typing import Any, Self, cast

import httpx

from app.providers.torbox.files import DownloadKind

DEFAULT_TORBOX_BASE_URL = "https://api.torbox.app/v1/api"
USER_AGENT = "Strmline/0.1.0"


class TorBoxAPIError(RuntimeError):
    """Raised when TorBox returns an error response."""


class TorBoxClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_TORBOX_BASE_URL,
        timeout: float = 20.0,
        http_client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            timeout=timeout,
            transport=transport,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._owns_client:
            await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = await self._client.get(
            self._url(path),
            headers=self._headers(),
            params=params,
        )
        payload = self._response_payload(response)

        if response.is_error:
            raise TorBoxAPIError(self._error_message(response.status_code, payload))

        if payload.get("success") is False:
            raise TorBoxAPIError(self._error_message(response.status_code, payload))
        return payload

    async def list_downloads(
        self, kind: DownloadKind, *, limit: int = 1000
    ) -> list[dict[str, Any]]:
        downloads: list[dict[str, Any]] = []
        offset = 0

        while True:
            payload = await self.get_json(
                f"/{kind}/mylist",
                params={
                    "limit": limit,
                    "offset": offset,
                    "bypass_cache": True,
                },
            )
            batch = self._require_data_list(payload)
            downloads.extend(batch)

            if len(batch) < limit:
                return downloads

            offset += limit

    def _url(self, path: str) -> str:
        normalized_path = path.strip("/")
        return f"{self._base_url}/{normalized_path}"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "User-Agent": USER_AGENT,
        }

    def _response_payload(self, response: httpx.Response) -> dict[str, Any]:
        payload = response.json()
        if not isinstance(payload, dict):
            msg = "TorBox response was not a JSON object."
            raise TorBoxAPIError(msg)
        return cast(dict[str, Any], payload)

    def _error_message(self, status_code: int, payload: dict[str, Any]) -> str:
        error = self._string_payload_value(payload.get("error"))
        detail = self._string_payload_value(payload.get("detail"))
        parts = [f"TorBox request failed with status {status_code}."]
        if error:
            parts.append(error)
        if detail:
            parts.append(detail)
        return " ".join(parts)

    def _string_payload_value(self, value: object) -> str:
        if isinstance(value, str):
            return value.strip()
        return ""

    def _require_data_list(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        data = payload.get("data")
        if not isinstance(data, list):
            msg = "TorBox response data was not a list."
            raise TorBoxAPIError(msg)

        typed_data: list[dict[str, Any]] = []
        for item in cast(list[object], data):
            if not isinstance(item, dict):
                msg = "TorBox response data contained a non-object item."
                raise TorBoxAPIError(msg)
            typed_data.append(cast(dict[str, Any], item))
        return typed_data
