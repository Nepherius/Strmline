from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, cast
from urllib.parse import urlencode

DownloadKind = Literal["torrents", "usenet", "webdl"]

DOWNLOAD_KINDS: tuple[DownloadKind, ...] = ("torrents", "usenet", "webdl")
ID_PARAM_BY_KIND: dict[DownloadKind, str] = {
    "torrents": "torrent_id",
    "usenet": "usenet_id",
    "webdl": "web_id",
}
VIDEO_EXTENSIONS = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".webm", ".wmv"}
SMALL_SAMPLE_MAX_BYTES = 250 * 1024 * 1024
SEPARATORS = re.compile(r"[._\-\s]+")


@dataclass(frozen=True, slots=True)
class TorBoxFile:
    kind: DownloadKind
    item_id: str
    file_id: str
    folder_name: str
    file_name: str
    path: str
    mime_type: str
    size: int | None


@dataclass(frozen=True, slots=True)
class ExtractedTorBoxFiles:
    files: tuple[TorBoxFile, ...]
    skipped_count: int


def extract_torbox_files(
    downloads: list[dict[str, Any]],
    kind: DownloadKind,
) -> ExtractedTorBoxFiles:
    files: list[TorBoxFile] = []
    skipped_count = 0

    for item in downloads:
        if item.get("cached") is False:
            skipped_count += 1
            continue
        item_files = item.get("files")
        if not isinstance(item_files, list):
            skipped_count += 1
            continue

        for raw_file in cast(list[object], item_files):
            if not isinstance(raw_file, dict):
                skipped_count += 1
                continue
            torbox_file = _build_torbox_file(item, cast(dict[str, Any], raw_file), kind)
            if torbox_file is None:
                skipped_count += 1
                continue
            files.append(torbox_file)

    return ExtractedTorBoxFiles(files=tuple(files), skipped_count=skipped_count)


def request_download_url(base_url: str, api_key: str, torbox_file: TorBoxFile) -> str:
    normalized_base_url = base_url.rstrip("/")
    params = urlencode(
        {
            "token": api_key,
            ID_PARAM_BY_KIND[torbox_file.kind]: torbox_file.item_id,
            "file_id": torbox_file.file_id,
            "redirect": "true",
        },
    )
    return f"{normalized_base_url}/{torbox_file.kind}/requestdl?{params}"


def _build_torbox_file(
    item: dict[str, Any],
    raw_file: dict[str, Any],
    kind: DownloadKind,
) -> TorBoxFile | None:
    item_id = _string_value(item.get("id"))
    file_id = _string_value(raw_file.get("id"))
    file_name = _basename(_first_string(raw_file, ("short_name", "name", "filename")))
    path = _string_value(raw_file.get("name")) or file_name
    mime_type = _string_value(raw_file.get("mimetype"))
    size = _int_value(raw_file.get("size"))

    if not item_id or not file_id or not file_name:
        return None
    if not _is_video(file_name, mime_type):
        return None
    if _is_sample_file(file_name, path, size):
        return None

    return TorBoxFile(
        kind=kind,
        item_id=item_id,
        file_id=file_id,
        folder_name=_string_value(item.get("name")),
        file_name=file_name,
        path=path,
        mime_type=mime_type,
        size=size,
    )


def _is_video(file_name: str, mime_type: str) -> bool:
    if mime_type:
        return mime_type.startswith("video/")
    lowered = file_name.casefold()
    return any(lowered.endswith(extension) for extension in VIDEO_EXTENSIONS)


def _is_sample_file(file_name: str, path: str, size: int | None) -> bool:
    name_tokens = _tokens(file_name)
    path_tokens = _tokens(path)
    if name_tokens in (["sample"], ["sample2"]):
        return True
    if "sample" not in name_tokens and "samples" not in path_tokens:
        return False
    return size is None or size <= SMALL_SAMPLE_MAX_BYTES


def _tokens(value: str) -> list[str]:
    stem = value.rsplit("/", maxsplit=1)[-1].rsplit("\\", maxsplit=1)[-1]
    stem = stem.rsplit(".", maxsplit=1)[0]
    return [token for token in SEPARATORS.split(stem.casefold()) if token]


def _first_string(data: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _string_value(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, int):
        return str(value)
    return ""


def _int_value(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    return None


def _basename(value: str) -> str:
    return cast(str, re.split(r"[\\/]", value)[-1]).strip()
