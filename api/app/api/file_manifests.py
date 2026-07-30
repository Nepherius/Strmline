from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import PurePath

from pydantic import BaseModel, Field

from app.providers.torbox.manifests import TorBoxManifestFile, TorBoxTorrentManifest


class MediaFileResponse(BaseModel):
    key: str
    name: str
    path: str
    size: int | None
    mime_type: str | None
    season: int | None
    episode: int | None
    version_count: int = Field(ge=1)


def _empty_media_files() -> list[MediaFileResponse]:
    return []


class MediaFileManifestResponse(BaseModel):
    ok: bool
    available: bool
    message: str
    total_files: int = Field(ge=0)
    displayed_files: int = Field(ge=0)
    source_count: int = Field(ge=0)
    files: list[MediaFileResponse] = Field(default_factory=_empty_media_files)


@dataclass(frozen=True, slots=True)
class LibraryManifestFile:
    library_entry_id: int
    source_key: str | None
    name: str
    path: str
    size: int | None
    mime_type: str | None
    season: int | None
    episode: int | None


def unavailable_manifest(message: str, *, ok: bool = True) -> MediaFileManifestResponse:
    return MediaFileManifestResponse(
        ok=ok,
        available=False,
        message=message,
        total_files=0,
        displayed_files=0,
        source_count=0,
    )


def torbox_manifest_response(manifest: TorBoxTorrentManifest) -> MediaFileManifestResponse:
    files = [_torbox_file_response(file, index) for index, file in enumerate(manifest.files)]
    return MediaFileManifestResponse(
        ok=True,
        available=True,
        message=f"Found {len(files)} included file(s).",
        total_files=len(files),
        displayed_files=len(files),
        source_count=1,
        files=files,
    )


def library_manifest_response(
    files: tuple[LibraryManifestFile, ...],
    *,
    collapse_episode_versions: bool,
) -> MediaFileManifestResponse:
    if not files:
        return unavailable_manifest("No synced files were found for this library entry.")

    displayed = (
        _collapse_episode_versions(files) if collapse_episode_versions else _individual_files(files)
    )
    source_count = len({file.source_key for file in files if file.source_key is not None})
    return MediaFileManifestResponse(
        ok=True,
        available=True,
        message=f"Found {len(files)} synced file(s).",
        total_files=len(files),
        displayed_files=len(displayed),
        source_count=source_count,
        files=displayed,
    )


def _torbox_file_response(file: TorBoxManifestFile, index: int) -> MediaFileResponse:
    return MediaFileResponse(
        key=file.external_id or f"file:{index}",
        name=file.name,
        path=file.path,
        size=file.size,
        mime_type=file.mime_type,
        season=None,
        episode=None,
        version_count=1,
    )


def _individual_files(files: tuple[LibraryManifestFile, ...]) -> list[MediaFileResponse]:
    return [_library_file_response(file, version_count=1) for file in files]


def _collapse_episode_versions(
    files: tuple[LibraryManifestFile, ...],
) -> list[MediaFileResponse]:
    episode_groups: dict[tuple[int, int], list[LibraryManifestFile]] = defaultdict(list)
    ungrouped: list[LibraryManifestFile] = []
    for file in files:
        if file.season is None or file.episode is None:
            ungrouped.append(file)
            continue
        episode_groups[(file.season, file.episode)].append(file)

    collapsed = [
        _library_file_response(
            min(group, key=_library_file_sort_key),
            version_count=len(group),
        )
        for _, group in sorted(episode_groups.items())
    ]
    collapsed.extend(
        _library_file_response(file, version_count=1)
        for file in sorted(ungrouped, key=_library_file_sort_key)
    )
    return collapsed


def _library_file_response(
    file: LibraryManifestFile,
    *,
    version_count: int,
) -> MediaFileResponse:
    return MediaFileResponse(
        key=(
            f"episode:{file.season}:{file.episode}"
            if file.season is not None and file.episode is not None
            else f"library:{file.library_entry_id}"
        ),
        name=file.name or PurePath(file.path).name,
        path=file.path,
        size=file.size,
        mime_type=file.mime_type,
        season=file.season,
        episode=file.episode,
        version_count=version_count,
    )


def _library_file_sort_key(file: LibraryManifestFile) -> tuple[str, int]:
    return file.path.casefold(), file.library_entry_id
