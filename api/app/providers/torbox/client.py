from __future__ import annotations

from types import TracebackType
from typing import Any, Self, cast

import httpx

from app.providers.torbox.files import DownloadKind

DEFAULT_TORBOX_BASE_URL = "https://api.torbox.app/v1/api"
USER_AGENT = "Strmline/0.1.0"


class TorBoxAPIError(RuntimeError):
    """Raised when TorBox returns an error response."""

    def __init__(self, message: str, *, error_code: str | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code


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

        if response.is_error or payload.get("success") is False:
            raise self._api_error(response.status_code, payload)
        return payload

    async def post_json(
        self,
        path: str,
        *,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        response = await self._client.post(
            self._url(path),
            headers={**self._headers(), "Content-Type": "application/json"},
            json=payload,
        )
        response_payload = self._response_payload(response)

        if response.is_error or response_payload.get("success") is False:
            raise self._api_error(response.status_code, response_payload)
        return response_payload

    async def post_form(
        self,
        path: str,
        *,
        data: dict[str, str],
    ) -> dict[str, Any]:
        form_files = {key: (None, value) for key, value in data.items()}
        response = await self._client.post(
            self._url(path),
            headers=self._headers(),
            files=form_files,
        )
        payload = self._response_payload(response)

        if response.is_error or payload.get("success") is False:
            raise self._api_error(response.status_code, payload)
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

    async def check_cached(self, hashes: list[str]) -> dict[str, bool]:
        """Check which torrent hashes are cached on TorBox.

        Batches hashes in groups of 100 per TorBox API recommendation.
        Returns a dict mapping each hash to its cached status.
        """
        if not hashes:
            return {}

        result: dict[str, bool] = {}
        batch_size = 100

        for start in range(0, len(hashes), batch_size):
            batch = hashes[start : start + batch_size]
            hash_param = ",".join(batch)
            try:
                payload = await self.get_json(
                    "/torrents/checkcached",
                    params={"hash": hash_param},
                )
            except TorBoxAPIError:
                for h in batch:
                    result[h] = False
                continue

            data = payload.get("data")
            if isinstance(data, dict):
                typed_data = cast(dict[str, Any], data)
                for h in batch:
                    entry = typed_data.get(h)
                    result[h] = entry is not None and entry is not False
            else:
                for h in batch:
                    result[h] = False

        return result

    async def create_torrent(
        self,
        *,
        magnet: str,
        name: str | None = None,
        add_only_if_cached: bool = True,
    ) -> dict[str, Any]:
        form_data = {
            "magnet": magnet,
            "add_only_if_cached": _bool_field(value=add_only_if_cached),
        }
        if name is not None and name.strip():
            form_data["name"] = name.strip()
        payload = await self.post_form("/torrents/createtorrent", data=form_data)
        data = payload.get("data")
        return cast(dict[str, Any], data) if isinstance(data, dict) else {}

    async def delete_torrent(self, torrent_id: str) -> None:
        await self.delete_download("torrents", torrent_id)

    async def delete_download(self, kind: DownloadKind, item_id: str) -> None:
        path, id_key = _delete_control(kind)
        _ = await self.post_json(
            path,
            payload={
                id_key: _numeric_id_payload(item_id),
                "operation": "Delete",
                "all": False,
            },
        )

    async def find_torrent_by_hash(self, info_hash: str) -> dict[str, Any] | None:
        normalized_hash = info_hash.casefold()
        matches = await self.find_torrents_by_hashes({normalized_hash})
        return matches.get(normalized_hash)

    async def find_torrents_by_hashes(self, info_hashes: set[str]) -> dict[str, dict[str, Any]]:
        normalized_hashes = {info_hash.casefold() for info_hash in info_hashes if info_hash}
        if not normalized_hashes:
            return {}
        matches: dict[str, dict[str, Any]] = {}
        for item in await self.list_downloads("torrents"):
            for matched_hash in _item_hashes(item).intersection(normalized_hashes):
                matches[matched_hash] = item
        return matches

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

    def _api_error(self, status_code: int, payload: dict[str, Any]) -> TorBoxAPIError:
        return TorBoxAPIError(
            self._error_message(status_code, payload),
            error_code=self._string_payload_value(payload.get("error")) or None,
        )

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


def _bool_field(*, value: bool) -> str:
    return "true" if value else "false"


def _delete_control(kind: DownloadKind) -> tuple[str, str]:
    if kind == "torrents":
        return "/torrents/controltorrent", "torrent_id"
    if kind == "usenet":
        return "/usenet/controlusenet", "usenet_id"
    return "/webdl/controlwebdownload", "web_id"


def _numeric_id_payload(value: str) -> int | str:
    return int(value) if value.isdecimal() else value


def _item_hashes(item: dict[str, Any]) -> set[str]:
    hashes: set[str] = set()
    item_hash = item.get("hash")
    if isinstance(item_hash, str) and item_hash.strip():
        hashes.add(item_hash.strip().casefold())
    alternative_hashes = item.get("alternative_hashes")
    if isinstance(alternative_hashes, list):
        for candidate in cast(list[object], alternative_hashes):
            if isinstance(candidate, str) and candidate.strip():
                hashes.add(candidate.strip().casefold())
    return hashes
