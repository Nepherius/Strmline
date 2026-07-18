from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import library as library_api
from app.db.models import MediaExternalIdentity, MediaItem
from app.db.repositories.media_metadata import (
    LibraryMediaPage,
    LibraryMediaRecord,
    LibraryPageEntry,
)


def _record(tmdb_id: str | None = None) -> LibraryMediaRecord:
    media_item = MediaItem(id=1, content_kind="series", title="Example", year=None)
    identity = None
    if tmdb_id is not None:
        identity = MediaExternalIdentity(
            media_item_id=1,
            provider="tmdb",
            provider_media_kind="tv",
            external_id=tmdb_id,
            authority="manual",
            authoritative=True,
        )
    return LibraryMediaRecord(media_item=media_item, tmdb_identity=identity)


@pytest.mark.asyncio
async def test_library_entries_defaults_to_fifty_and_reports_more_pages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRepository:
        def __init__(self, _session: AsyncSession) -> None:
            pass

        async def library_page(self, options: object) -> LibraryMediaPage:
            assert options == library_api.LibraryPageOptions(
                limit=50,
                category=None,
                query="",
                sort_key="title",
                direction="asc",
                include_overview=True,
                cursor=None,
            )
            return LibraryMediaPage(
                entries=(
                    LibraryPageEntry(
                        media_item_id=1,
                        title="First Movie",
                        category="movies",
                        relative_prefix="movies/First Movie",
                        file_count=1,
                        tmdb_id=None,
                    ),
                ),
                next_cursor="next-page",
                total_matches=1001,
                total_files=5000,
                category_counts={"movies": 501, "shows": 400, "anime": 100},
            )

    monkeypatch.setattr(library_api, "MediaMetadataRepository", FakeRepository)

    response = await library_api.library_entries(
        AsyncMock(spec=AsyncSession),
        tmp_path,
        library_api.LibraryEntryPageRequest(),
    )

    assert response.limit == 50
    assert response.total == 1001
    assert response.has_more is True
    assert response.next_cursor == "next-page"
    assert response.total_files == 5000
    assert response.entries[0].title == "First Movie"


@pytest.mark.asyncio
async def test_library_poster_uses_stable_media_id_and_releases_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    poster = tmp_path / "artwork" / "tmdb-123.jpg"
    poster.parent.mkdir()
    _ = poster.write_bytes(b"poster")
    session = AsyncMock(spec=AsyncSession)

    class FakeRepository:
        def __init__(self, _session: AsyncSession) -> None:
            pass

        async def find_for_media_item(self, media_item_id: int) -> LibraryMediaRecord:
            assert media_item_id == 1
            return _record("123")

    monkeypatch.setattr(library_api, "MediaMetadataRepository", FakeRepository)

    def fake_poster_for_tmdb_id(_root: Path, _tmdb_id: str) -> Path:
        return poster

    monkeypatch.setattr(
        library_api,
        "poster_for_tmdb_id",
        fake_poster_for_tmdb_id,
    )

    response = await library_api.library_poster(1, session, tmp_path)

    session.close.assert_awaited_once()
    assert response.path == poster


@pytest.mark.asyncio
async def test_update_entry_tmdb_id_is_authoritative_and_refreshes_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock(spec=AsyncSession)
    current = _record()
    updated = _record("12345")

    class FakeRepository:
        def __init__(self, _session: AsyncSession) -> None:
            pass

        async def find_for_library_prefix(self, relative_prefix: str) -> LibraryMediaRecord:
            assert relative_prefix == "shows/Example"
            return current

        async def set_tmdb_id_for_media_item(
            self,
            media_item_id: int,
            tmdb_id: str,
        ) -> LibraryMediaRecord:
            assert media_item_id == 1
            assert tmdb_id == "12345"
            return updated

    refresh = AsyncMock(return_value=1)
    monkeypatch.setattr(library_api, "MediaMetadataRepository", FakeRepository)
    monkeypatch.setattr(
        library_api,
        "require_matching_media_record",
        AsyncMock(return_value=current),
    )
    monkeypatch.setattr(library_api, "refresh_tmdb_metadata", refresh)
    monkeypatch.setattr(library_api, "effective_tmdb_key", AsyncMock(return_value="tmdb-key"))

    response = await library_api.update_entry_tmdb_id(
        library_api.LibraryTmdbIdUpdateRequest(
            category="shows",
            relative_path="shows/Example",
            media_item_id=1,
            tmdb_id=12345,
        ),
        session,
        tmp_path,
    )

    assert response.tmdb_id == 12345
    assert response.refreshed_posters == 1
    assert "metadata" in response.message
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()
    refresh.assert_awaited_once()
    refresh_call = refresh.await_args
    assert refresh_call is not None
    assert refresh_call.kwargs["media_item_id"] == 1
    assert refresh_call.kwargs["library_root"] == tmp_path


@pytest.mark.asyncio
async def test_update_entry_tmdb_id_rejects_stale_path_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock(spec=AsyncSession)
    stale_record = _record()
    stale_record.media_item.id = 2

    class FakeRepository:
        def __init__(self, _session: AsyncSession) -> None:
            pass

        async def find_for_library_prefix(self, _relative_prefix: str) -> LibraryMediaRecord:
            return stale_record

    monkeypatch.setattr(library_api, "MediaMetadataRepository", FakeRepository)
    monkeypatch.setattr(
        library_api,
        "require_matching_media_record",
        AsyncMock(
            side_effect=HTTPException(
                status_code=409,
                detail="Library entry identity no longer matches its current path.",
            )
        ),
    )

    with pytest.raises(HTTPException, match="current path"):
        _ = await library_api.update_entry_tmdb_id(
            library_api.LibraryTmdbIdUpdateRequest(
                category="shows",
                relative_path="shows/Example",
                media_item_id=1,
                tmdb_id=12345,
            ),
            session,
            tmp_path,
        )


@pytest.mark.asyncio
async def test_update_entry_tmdb_id_rolls_back_when_refresh_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock(spec=AsyncSession)
    current = _record()

    class FakeRepository:
        def __init__(self, _session: AsyncSession) -> None:
            pass

        async def find_for_library_prefix(self, _relative_prefix: str) -> LibraryMediaRecord:
            return current

        async def set_tmdb_id_for_media_item(
            self,
            _media_item_id: int,
            _tmdb_id: str,
        ) -> LibraryMediaRecord:
            return _record("12345")

    monkeypatch.setattr(library_api, "MediaMetadataRepository", FakeRepository)
    monkeypatch.setattr(
        library_api,
        "require_matching_media_record",
        AsyncMock(return_value=current),
    )
    monkeypatch.setattr(
        library_api,
        "effective_tmdb_key",
        AsyncMock(return_value="tmdb-key"),
    )
    monkeypatch.setattr(
        library_api,
        "refresh_tmdb_metadata",
        AsyncMock(side_effect=library_api.MetadataRefreshError("TMDB ID was not found.")),
    )

    with pytest.raises(HTTPException, match="TMDB ID was not found"):
        _ = await library_api.update_entry_tmdb_id(
            library_api.LibraryTmdbIdUpdateRequest(
                category="shows",
                relative_path="shows/Example",
                media_item_id=1,
                tmdb_id=12345,
            ),
            session,
            tmp_path,
        )

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
