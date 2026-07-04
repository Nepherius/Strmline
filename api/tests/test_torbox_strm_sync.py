from pathlib import Path
from typing import Any

import pytest

from app.providers.torbox.files import DownloadKind
from app.resolver.manifest import resolve_manifest_target
from app.sync.torbox_strm import DirectTorBoxStrmSync, ResolverUrlConfig


class FakeTorBoxClient:
    async def list_downloads(
        self, kind: DownloadKind, *, limit: int = 1000
    ) -> list[dict[str, Any]]:
        _ = limit
        if kind != "torrents":
            return []
        return [
            {
                "id": 1,
                "name": "Movie.Name.2024",
                "cached": True,
                "files": [
                    {
                        "id": 2,
                        "short_name": "Movie.Name.2024.1080p.mkv",
                        "name": "Movie.Name.2024/Movie.Name.2024.1080p.mkv",
                        "mimetype": "video/x-matroska",
                        "size": 1_000_000_000,
                    },
                ],
            },
        ]


class MultiFileTorBoxClient:
    async def list_downloads(
        self, kind: DownloadKind, *, limit: int = 1000
    ) -> list[dict[str, Any]]:
        _ = limit
        if kind != "torrents":
            return []
        return [
            {
                "id": 1,
                "name": "Movies",
                "cached": True,
                "files": [
                    {
                        "id": 2,
                        "short_name": "First.Movie.2024.mkv",
                        "mimetype": "video/x-matroska",
                    },
                    {
                        "id": 3,
                        "short_name": "Second.Movie.2024.mkv",
                        "mimetype": "video/x-matroska",
                    },
                ],
            },
        ]


class DuplicatePathTorBoxClient:
    async def list_downloads(
        self, kind: DownloadKind, *, limit: int = 1000
    ) -> list[dict[str, Any]]:
        _ = limit
        if kind != "torrents":
            return []
        return [
            {
                "id": 1,
                "name": "Movie.Name.2024",
                "cached": True,
                "files": [
                    {
                        "id": 2,
                        "short_name": "Movie.Name.2024.1080p.mkv",
                        "mimetype": "video/x-matroska",
                    },
                    {
                        "id": 3,
                        "short_name": "Movie.Name.2024.1080p.mkv",
                        "mimetype": "video/x-matroska",
                    },
                ],
            },
        ]


@pytest.mark.asyncio
async def test_direct_torbox_strm_sync_writes_playable_strm_files(tmp_path: Path) -> None:
    sync = DirectTorBoxStrmSync(
        client=FakeTorBoxClient(),
        api_key="test-token",
        torbox_base_url="https://api.torbox.app/v1/api",
        library_root=tmp_path,
    )

    result = await sync.run(kinds=("torrents",))

    expected_path = tmp_path / "movies" / "Movie Name (2024)" / "Movie Name (2024).strm"
    assert result.scanned_files == 1
    assert result.written_files == 1
    assert result.skipped_files == 0
    assert result.written_paths == (expected_path.resolve(strict=False),)
    assert result.synced_files[0].path == expected_path.resolve(strict=False)
    assert result.synced_files[0].title == "Movie Name"
    assert result.synced_files[0].category == "movies"
    assert result.synced_files[0].provider_item_id == "1"
    assert result.synced_files[0].provider_file_id == "2"
    assert expected_path.read_text(encoding="utf-8") == (
        "https://api.torbox.app/v1/api/torrents/requestdl?"
        "token=test-token&torrent_id=1&file_id=2&redirect=true\n"
    )


@pytest.mark.asyncio
async def test_direct_torbox_strm_sync_can_limit_written_files(tmp_path: Path) -> None:
    sync = DirectTorBoxStrmSync(
        client=MultiFileTorBoxClient(),
        api_key="test-token",
        torbox_base_url="https://api.torbox.app/v1/api",
        library_root=tmp_path,
    )

    result = await sync.run(kinds=("torrents",), max_files=1)

    assert result.scanned_files == 1
    assert result.written_files == 1
    assert len(result.written_paths) == 1


@pytest.mark.asyncio
async def test_direct_torbox_strm_sync_counts_unique_output_paths(tmp_path: Path) -> None:
    sync = DirectTorBoxStrmSync(
        client=DuplicatePathTorBoxClient(),
        api_key="test-token",
        torbox_base_url="https://api.torbox.app/v1/api",
        library_root=tmp_path,
    )

    result = await sync.run(kinds=("torrents",))

    assert result.scanned_files == 2
    assert result.written_files == 1
    assert len(result.written_paths) == 2


@pytest.mark.asyncio
async def test_torbox_strm_sync_writes_resolver_urls_and_manifest(tmp_path: Path) -> None:
    resolver_token = "resolver-secret"  # noqa: S105
    sync = DirectTorBoxStrmSync(
        client=FakeTorBoxClient(),
        api_key="test-token",
        torbox_base_url="https://api.torbox.app/v1/api",
        library_root=tmp_path,
        resolver=ResolverUrlConfig(base_url="http://strmline:8080", token=resolver_token),
    )

    result = await sync.run(kinds=("torrents",))

    expected_path = tmp_path / "movies" / "Movie Name (2024)" / "Movie Name (2024).strm"
    strm_content = expected_path.read_text(encoding="utf-8")
    assert result.manifest_path == tmp_path / ".strmline" / "resolver_manifest.json"
    assert strm_content.startswith("http://strmline:8080/play/")
    assert f"token={resolver_token}" in strm_content
    entry_id = strm_content.split("/play/", maxsplit=1)[1].split("?", maxsplit=1)[0]
    assert resolve_manifest_target(tmp_path, entry_id) == (
        "https://api.torbox.app/v1/api/torrents/requestdl?"
        "token=test-token&torrent_id=1&file_id=2&redirect=true"
    )
