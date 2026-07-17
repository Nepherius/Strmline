from pathlib import Path
from typing import Any

import pytest

from app.providers.torbox.files import DownloadKind
from app.sync.torbox_strm import DirectTorBoxStrmSync


class BlurayTorBoxClient:
    async def list_downloads(
        self, kind: DownloadKind, *, limit: int = 1000
    ) -> list[dict[str, Any]]:
        _ = limit
        if kind != "torrents":
            return []
        folder = "The.Witch.Part.1.The.Subversion.2018.KOREAN.1080p.BluRay"
        return [
            {
                "id": 10,
                "name": folder,
                "cached": True,
                "files": [
                    {
                        "id": 20,
                        "name": f"{folder}/BDMV/STREAM/00000.m2ts",
                        "size": 2_500_000,
                    },
                    {
                        "id": 21,
                        "name": f"{folder}/BDMV/STREAM/00001.m2ts",
                        "size": 29_500_000_000,
                    },
                    {
                        "id": 22,
                        "name": f"{folder}/BDMV/STREAM/00002.m2ts",
                        "size": 140_000_000,
                    },
                ],
            }
        ]


@pytest.mark.asyncio
async def test_bluray_sync_writes_one_feature_using_release_title(tmp_path: Path) -> None:
    sync = DirectTorBoxStrmSync(
        client=BlurayTorBoxClient(),
        api_key="test-token",
        torbox_base_url="https://api.torbox.app/v1/api",
        library_root=tmp_path,
    )

    result = await sync.run(kinds=("torrents",))

    assert result.scanned_files == 1
    assert result.written_files == 1
    assert result.skipped_files == 2
    assert result.synced_files[0].title == "The Witch Part 1 The Subversion"
    assert result.synced_files[0].year == 2018
    assert result.synced_files[0].provider_file_name == "00001.m2ts"
    assert result.written_paths[0].relative_to(tmp_path).as_posix() == (
        "movies/The Witch Part 1 The Subversion (2018)/The Witch Part 1 The Subversion (2018).strm"
    )
