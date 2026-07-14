from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import library as library_api


@pytest.mark.asyncio
async def test_library_poster_releases_database_session_before_file_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    poster = tmp_path / "artwork" / "tmdb-123.jpg"
    poster.parent.mkdir()
    _ = poster.write_bytes(b"poster")
    session = AsyncMock(spec=AsyncSession)
    record = SimpleNamespace(media_item=SimpleNamespace(tmdb_id="123"))

    class FakeRepository:
        def __init__(self, _session: AsyncSession) -> None:
            pass

        async def find_for_library_prefix(self, _relative_path: str) -> object:
            return record

    monkeypatch.setattr(library_api, "MediaMetadataRepository", FakeRepository)
    monkeypatch.setattr(library_api, "poster_for_tmdb_id", lambda _root, _tmdb_id: poster)

    response = await library_api.library_poster("shows/Example", session, tmp_path)

    session.close.assert_awaited_once()
    assert response.path == poster
