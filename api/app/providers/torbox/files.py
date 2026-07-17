from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Literal, cast
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

DownloadKind = Literal["torrents", "usenet", "webdl"]

DOWNLOAD_KINDS: tuple[DownloadKind, ...] = ("torrents", "usenet", "webdl")
ID_PARAM_BY_KIND: dict[DownloadKind, str] = {
    "torrents": "torrent_id",
    "usenet": "usenet_id",
    "webdl": "web_id",
}
VIDEO_EXTENSIONS = {
    ".avi",
    ".m2ts",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".webm",
    ".wmv",
}
SMALL_SAMPLE_MAX_BYTES = 250 * 1024 * 1024
MIN_BLURAY_STREAM_FILES = 2
SEPARATORS = re.compile(r"[._\-\s]+")
PACK_EXTRA = re.compile(r"(?i)^s\d{1,2}[\s._-]*(?:op|ed|sp)\d*(?:\D|$)")
NAMED_EXTRA_TOKENS = {"ncop", "nced", "opening", "ending"}


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

    @property
    def library_name(self) -> str:
        if is_bluray_stream_path(self.path) and self.folder_name:
            return self.folder_name
        return self.file_name


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

        extracted_item_files: list[TorBoxFile] = []
        for raw_file in cast(list[object], item_files):
            if not isinstance(raw_file, dict):
                skipped_count += 1
                continue
            torbox_file = _build_torbox_file(item, cast(dict[str, Any], raw_file), kind)
            if torbox_file is None:
                skipped_count += 1
                continue
            extracted_item_files.append(torbox_file)
        selected_item_files, bluray_skipped = _select_bluray_feature_files(extracted_item_files)
        files.extend(selected_item_files)
        skipped_count += bluray_skipped

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


def torrent_info_hash(item: dict[str, Any]) -> str | None:
    value = item.get("hash")
    if isinstance(value, str) and value.strip():
        return value.strip().casefold()
    alternative_hashes = item.get("alternative_hashes")
    if not isinstance(alternative_hashes, list):
        return None
    for candidate in cast(list[object], alternative_hashes):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip().casefold()
    return None


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
    if _is_sample_file(file_name, path, size) or _is_pack_extra(file_name):
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


def is_bluray_stream_path(path: str) -> bool:
    return _bluray_stream_group(path) is not None


def _select_bluray_feature_files(
    files: list[TorBoxFile],
) -> tuple[list[TorBoxFile], int]:
    groups: dict[str, list[TorBoxFile]] = {}
    for torbox_file in files:
        group = _bluray_stream_group(torbox_file.path)
        if group is not None:
            groups.setdefault(group, []).append(torbox_file)

    selected_by_group: dict[str, TorBoxFile] = {}
    skipped_count = 0
    for group, candidates in groups.items():
        sized_candidates = [candidate for candidate in candidates if candidate.size is not None]
        if len(candidates) < MIN_BLURAY_STREAM_FILES or not sized_candidates:
            continue
        selected = max(
            sized_candidates,
            key=lambda candidate: candidate.size or 0,
        )
        selected_by_group[group] = selected
        skipped_count += len(candidates) - 1
        logger.debug(
            "Selected Blu-ray feature item_id=%s file=%s size=%s from %d stream(s).",
            selected.item_id,
            selected.file_name,
            selected.size,
            len(candidates),
        )

    selected_files = [
        torbox_file
        for torbox_file in files
        if (group := _bluray_stream_group(torbox_file.path)) not in selected_by_group
        or torbox_file is selected_by_group[group]
    ]
    return selected_files, skipped_count


def _bluray_stream_group(path: str) -> str | None:
    parts = [part for part in re.split(r"[\\/]", path) if part]
    if not parts or not parts[-1].casefold().endswith(".m2ts"):
        return None
    for index in range(len(parts) - 2):
        if parts[index].casefold() == "bdmv" and parts[index + 1].casefold() == "stream":
            return "/".join(part.casefold() for part in parts[: index + 1])
    return None


def _is_sample_file(file_name: str, path: str, size: int | None) -> bool:
    name_tokens = _tokens(file_name)
    path_tokens = _tokens(path)
    if name_tokens in (["sample"], ["sample2"]):
        return True
    if "sample" not in name_tokens and "samples" not in path_tokens:
        return False
    return size is None or size <= SMALL_SAMPLE_MAX_BYTES


def _is_pack_extra(file_name: str) -> bool:
    stem = file_name.rsplit("/", maxsplit=1)[-1].rsplit("\\", maxsplit=1)[-1]
    stem = stem.rsplit(".", maxsplit=1)[0]
    if PACK_EXTRA.match(stem):
        return True
    return any(token in NAMED_EXTRA_TOKENS for token in _tokens(file_name))


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
