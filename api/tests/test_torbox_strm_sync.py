from pathlib import Path
from typing import Any

import pytest

from app.providers.torbox.files import DownloadKind
from app.sync.torbox_strm import DirectTorBoxStrmSync


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
