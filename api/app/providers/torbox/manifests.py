from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath
from typing import Any, cast

from app.domain.normalization import normalize_info_hash


@dataclass(frozen=True, slots=True)
class TorBoxManifestFile:
    external_id: str | None
    name: str
    path: str
    size: int | None
    mime_type: str | None


@dataclass(frozen=True, slots=True)
class TorBoxTorrentManifest:
    info_hash: str
    name: str | None
    files: tuple[TorBoxManifestFile, ...]


def torrent_manifest_from_cached_payload(
    payload: dict[str, Any],
    info_hash: str,
) -> TorBoxTorrentManifest | None:
    normalized_hash = normalize_info_hash(info_hash)
    if normalized_hash is None:
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    cached_item = _cached_item(cast(dict[str, Any], data), normalized_hash)
    if cached_item is None:
        return None
    return _torrent_manifest(cached_item, normalized_hash)


def torrent_manifest_from_download(
    download: dict[str, Any],
    info_hash: str | None,
) -> TorBoxTorrentManifest | None:
    normalized_hash = normalize_info_hash(info_hash) or "unknown"
    return _torrent_manifest(download, normalized_hash)


def _cached_item(data: dict[str, Any], info_hash: str) -> dict[str, Any] | None:
    for key, value in data.items():
        if key.casefold() != info_hash or not isinstance(value, dict):
            continue
        return cast(dict[str, Any], value)
    return None


def _torrent_manifest(
    item: dict[str, Any],
    info_hash: str,
) -> TorBoxTorrentManifest | None:
    raw_files = item.get("files")
    if not isinstance(raw_files, list):
        return None
    files = tuple(
        manifest_file
        for index, raw_file in enumerate(cast(list[object], raw_files))
        if isinstance(raw_file, dict)
        and (manifest_file := _manifest_file(cast(dict[str, Any], raw_file), index)) is not None
    )
    if not files:
        return None
    return TorBoxTorrentManifest(
        info_hash=info_hash,
        name=_optional_string(item.get("name")),
        files=tuple(sorted(files, key=lambda file: (file.name.casefold(), file.path.casefold()))),
    )


def _manifest_file(raw_file: dict[str, Any], index: int) -> TorBoxManifestFile | None:
    path = _first_string(raw_file, ("name", "path", "filename", "short_name"))
    if path is None:
        return None
    name = _first_string(raw_file, ("short_name", "filename")) or PurePath(path).name
    return TorBoxManifestFile(
        external_id=_identifier(raw_file.get("id")) or f"file:{index}",
        name=name,
        path=path,
        size=_optional_int(raw_file.get("size")),
        mime_type=_optional_string(raw_file.get("mimetype") or raw_file.get("mime_type")),
    )


def _first_string(payload: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = _optional_string(payload.get(key))
        if value is not None:
            return value
    return None


def _optional_string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _identifier(value: object) -> str | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return _optional_string(value)
