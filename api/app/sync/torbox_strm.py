from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.library.entries import LibraryEntry
from app.library.naming import library_entry_from_file_name
from app.library.strm_writer import write_strm_file
from app.providers.torbox.files import (
    DOWNLOAD_KINDS,
    DownloadKind,
    TorBoxFile,
    extract_torbox_files,
    request_download_url,
)
from app.resolver.manifest import (
    ResolverManifestEntry,
    resolver_entry_id,
    resolver_playback_url,
    write_manifest_entries,
)


class TorBoxDownloadClient(Protocol):
    async def list_downloads(
        self, kind: DownloadKind, *, limit: int = 1000
    ) -> list[dict[str, Any]]:
        """Return raw TorBox download items for a download type."""
        ...


@dataclass(frozen=True, slots=True)
class TorBoxStrmSyncResult:
    scanned_files: int
    written_files: int
    skipped_files: int
    written_paths: tuple[Path, ...]
    synced_files: tuple[SyncedStrmFile, ...]
    manifest_path: Path | None = None
    partial: bool = False


@dataclass(frozen=True, slots=True)
class SyncedStrmFile:
    path: Path
    entry_id: str
    category: str
    title: str
    year: int | None
    season_number: int | None
    episode_number: int | None
    provider: str
    provider_item_id: str
    provider_file_id: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class ResolverUrlConfig:
    base_url: str
    token: str


class TorBoxStrmSync:
    def __init__(
        self,
        *,
        client: TorBoxDownloadClient,
        api_key: str,
        torbox_base_url: str,
        library_root: Path,
        resolver: ResolverUrlConfig | None = None,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._torbox_base_url = torbox_base_url
        self._library_root = library_root
        self._resolver = resolver

    async def run(
        self,
        kinds: tuple[DownloadKind, ...] = DOWNLOAD_KINDS,
        *,
        max_files: int | None = None,
    ) -> TorBoxStrmSyncResult:
        if max_files is not None and max_files < 1:
            msg = "max_files must be positive."
            raise ValueError(msg)

        written_paths: list[Path] = []
        synced_files: list[SyncedStrmFile] = []
        manifest_entries: list[ResolverManifestEntry] = []
        scanned_files = 0
        skipped_files = 0

        for kind in kinds:
            downloads = await self._client.list_downloads(kind)
            extracted = extract_torbox_files(downloads, kind)
            skipped_files += extracted.skipped_count

            for torbox_file in extracted.files:
                if max_files is not None and len(written_paths) >= max_files:
                    return self._result(
                        scanned_files,
                        skipped_files,
                        written_paths,
                        synced_files,
                        manifest_entries,
                        partial=True,
                    )
                scanned_files += 1
                entry_id = resolver_entry_id(torbox_file)
                playback_url = self._playback_url(torbox_file, entry_id, manifest_entries)
                entry = library_entry_from_file_name(
                    torbox_file.file_name,
                    playback_url,
                    torbox_file.folder_name,
                )
                written_path = write_strm_file(self._library_root, entry)
                written_paths.append(written_path)
                synced_files.append(_synced_file(written_path, entry_id, entry, torbox_file))

        return self._result(
            scanned_files,
            skipped_files,
            written_paths,
            synced_files,
            manifest_entries,
        )

    def _playback_url(
        self,
        torbox_file: TorBoxFile,
        entry_id: str,
        manifest_entries: list[ResolverManifestEntry],
    ) -> str:
        direct_url = request_download_url(
            self._torbox_base_url,
            self._api_key,
            torbox_file,
        )
        if self._resolver is None:
            return direct_url

        manifest_entries.append(
            ResolverManifestEntry(
                entry_id=entry_id,
                target_url=direct_url,
            )
        )
        return resolver_playback_url(self._resolver.base_url, self._resolver.token, entry_id)

    def _result(
        self,
        scanned_files: int,
        skipped_files: int,
        written_paths: list[Path],
        synced_files: list[SyncedStrmFile],
        manifest_entries: list[ResolverManifestEntry],
        *,
        partial: bool = False,
    ) -> TorBoxStrmSyncResult:
        manifest_path = None
        if manifest_entries:
            manifest_path = write_manifest_entries(self._library_root, manifest_entries)
        unique_written_paths = set(written_paths)
        return TorBoxStrmSyncResult(
            scanned_files=scanned_files,
            written_files=len(unique_written_paths),
            skipped_files=skipped_files,
            written_paths=tuple(written_paths),
            synced_files=tuple(synced_files),
            manifest_path=manifest_path,
            partial=partial,
        )


def _synced_file(
    path: Path,
    entry_id: str,
    entry: LibraryEntry,
    torbox_file: TorBoxFile,
) -> SyncedStrmFile:
    return SyncedStrmFile(
        path=path,
        entry_id=entry_id,
        category=entry.category,
        title=entry.title,
        year=entry.year,
        season_number=entry.season_number,
        episode_number=entry.episode_number,
        provider="torbox",
        provider_item_id=torbox_file.item_id,
        provider_file_id=torbox_file.file_id,
        content_hash=hashlib.sha256(entry.resolver_url.encode("utf-8")).hexdigest(),
    )


DirectTorBoxStrmSync = TorBoxStrmSync
