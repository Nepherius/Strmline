from pathlib import Path
from typing import Any

import pytest

from app.providers.torbox.files import DownloadKind
from app.sync.media_identity import MediaIdentity
from app.sync.torbox_strm import DirectTorBoxStrmSync


class IdentityTorBoxClient:
    async def list_downloads(
        self, kind: DownloadKind, *, limit: int = 1000
    ) -> list[dict[str, Any]]:
        _ = limit
        if kind != "torrents":
            return []
        return [
            {
                "id": 1,
                "name": "Ascendance of a Bookworm",
                "cached": True,
                "files": [
                    {
                        "id": 2,
                        "short_name": "Ascendance.of.a.Bookworm.S01E01.mkv",
                        "mimetype": "video/x-matroska",
                    }
                ],
            }
        ]


class FakeMediaIdentityResolver:
    async def resolve(self, parsed_title: str, year: int | None, category: str) -> MediaIdentity:
        _ = (parsed_title, year, category)
        return MediaIdentity(
            tmdb_id="91768",
            title="Ascendance of a Bookworm",
            year=2019,
            media_type="tv",
        )


@pytest.mark.asyncio
async def test_torbox_sync_uses_tmdb_tv_identity_for_episode_category(tmp_path: Path) -> None:
    sync = DirectTorBoxStrmSync(
        client=IdentityTorBoxClient(),
        api_key="test-token",
        torbox_base_url="https://api.torbox.app/v1/api",
        library_root=tmp_path,
        media_identity_resolver=FakeMediaIdentityResolver(),
    )

    result = await sync.run(kinds=("torrents",))

    assert result.synced_files[0].category == "shows"
    assert result.synced_files[0].tmdb_id == "91768"
