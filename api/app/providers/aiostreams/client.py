from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import quote, urlparse

import httpx


class AioStreamsClientError(RuntimeError):
    """Raised when a safe AIOStreams request fails."""


@dataclass(frozen=True, slots=True)
class AioStreamsManifest:
    id: str | None
    name: str | None
    version: str | None
    resources: tuple[str, ...]
    types: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AioStreamsStream:
    name: str | None
    title: str | None
    description: str | None
    url: str | None
    info_hash: str | None
    file_idx: int | None
    behavior_hints: dict[str, Any]
    raw: dict[str, Any]

    @property
    def playable(self) -> bool:
        return self.url is not None or self.info_hash is not None


@dataclass(frozen=True, slots=True)
class AioStreamsTriggerResult:
    status_code: int
    redirected: bool


class AioStreamsClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def manifest(self) -> AioStreamsManifest:
        payload = await self._get_json(_join_url(self._base_url, "manifest.json"))
        return _manifest_from_payload(payload)

    async def streams(self, *, media_type: str, media_id: str) -> tuple[AioStreamsStream, ...]:
        stream_path = f"stream/{quote(media_type, safe='')}/{quote(media_id, safe='')}.json"
        payload = await self._get_json(_join_url(self._base_url, stream_path))
        return _streams_from_payload(payload)

    async def trigger_stream_url(self, url: str) -> AioStreamsTriggerResult:
        if not _is_safe_trigger_url(url):
            raise AioStreamsClientError("AIOStreams stream trigger URL is not allowed.")
        try:
            async with (
                httpx.AsyncClient(
                    timeout=self._timeout_seconds,
                    transport=self._transport,
                    follow_redirects=False,
                ) as client,
                client.stream(
                    "GET",
                    url,
                    headers={"Range": "bytes=0-0"},
                ) as response,
            ):
                if response.is_error:
                    raise AioStreamsClientError("AIOStreams stream trigger failed.")
                return AioStreamsTriggerResult(
                    status_code=response.status_code,
                    redirected=response.is_redirect,
                )
        except httpx.HTTPError as error:
            raise AioStreamsClientError("AIOStreams stream trigger failed.") from error

    async def _get_json(self, url: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.get(url)
        except httpx.HTTPError as error:
            raise AioStreamsClientError("AIOStreams request failed.") from error
        if response.is_error:
            raise AioStreamsClientError("AIOStreams request failed.")
        try:
            payload: object = response.json()
        except ValueError as error:
            raise AioStreamsClientError("AIOStreams response was not JSON.") from error
        if not isinstance(payload, dict):
            raise AioStreamsClientError("AIOStreams response was not an object.")
        return cast(dict[str, Any], payload)


def _join_url(base_url: str, path: str) -> str:
    if base_url.endswith("/manifest.json") and path == "manifest.json":
        return base_url
    normalized_base = base_url.removesuffix("/manifest.json")
    return f"{normalized_base}/{path.lstrip('/')}"


def _is_safe_trigger_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme.casefold() not in {"http", "https"}:
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    hostname = parsed.hostname
    if hostname is None:
        return False
    if hostname.casefold() == "localhost":
        return False
    try:
        ip_address = ipaddress.ip_address(hostname)
    except ValueError:
        return True
    return not (
        ip_address.is_private
        or ip_address.is_loopback
        or ip_address.is_link_local
        or ip_address.is_reserved
        or ip_address.is_unspecified
    )


def _manifest_from_payload(payload: dict[str, Any]) -> AioStreamsManifest:
    return AioStreamsManifest(
        id=_optional_str(payload.get("id")),
        name=_optional_str(payload.get("name")),
        version=_optional_str(payload.get("version")),
        resources=_str_tuple(payload.get("resources")),
        types=_str_tuple(payload.get("types")),
    )


def _streams_from_payload(payload: dict[str, Any]) -> tuple[AioStreamsStream, ...]:
    raw_streams = payload.get("streams")
    if not isinstance(raw_streams, list):
        raise AioStreamsClientError("AIOStreams stream response did not include streams.")
    return tuple(
        _stream_from_payload(cast(dict[str, Any], raw_stream))
        for raw_stream in cast(list[object], raw_streams)
        if isinstance(raw_stream, dict)
    )


def _stream_from_payload(payload: dict[str, Any]) -> AioStreamsStream:
    behavior_hints = payload.get("behaviorHints")
    safe_behavior_hints = (
        cast(dict[str, Any], behavior_hints) if isinstance(behavior_hints, dict) else {}
    )
    return AioStreamsStream(
        name=_optional_str(payload.get("name")),
        title=_optional_str(payload.get("title")),
        description=_optional_str(payload.get("description")),
        url=_optional_str(payload.get("url")),
        info_hash=_optional_str(payload.get("infoHash")),
        file_idx=_optional_int(payload.get("fileIdx")),
        behavior_hints=safe_behavior_hints,
        raw=payload,
    )


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _str_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in cast(list[object], value) if isinstance(item, str))
