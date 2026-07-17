from pathlib import Path
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MediaItem
from app.db.repositories.media_identity import (
    MediaIdentityRepository,
    MediaIdentityWrite,
    SourceBindingWrite,
)
from app.db.repositories.sync_state import SyncLibraryStateRepository
from app.domain.media_identity import IdentityAuthority
from app.sync.torbox_strm import SyncedStrmFile


class CapturingIdentityRepository:
    def __init__(self, existing: MediaItem) -> None:
        self.existing = existing
        self.identity_write: MediaIdentityWrite | None = None
        self.source_write: SourceBindingWrite | None = None

    async def ensure_media(self, write: MediaIdentityWrite) -> MediaItem:
        self.identity_write = write
        return self.existing

    async def bind_sources(
        self,
        media_item: MediaItem,
        write: SourceBindingWrite,
    ) -> None:
        assert media_item is self.existing
        self.source_write = write


@pytest.mark.asyncio
async def test_sync_delegates_identity_without_mutating_complete_media(tmp_path: Path) -> None:
    existing_item = MediaItem(
        id=10,
        content_kind="series",
        title="Ascendance of a Bookworm",
        year=2019,
    )
    repository = CapturingIdentityRepository(existing_item)
    synced_file = SyncedStrmFile(
        path=tmp_path / "anime" / "Ascendance of a Bookworm" / "Season 01" / "S01E01.strm",
        entry_id="entry-id",
        category="anime",
        title="Incorrect provider title",
        source_title="Ascendance of a Bookworm 01 JP BD Hi10",
        year=2024,
        season_number=1,
        episode_number=1,
        provider="torrents",
        provider_item_id="1",
        provider_file_id="2",
        content_hash="content-hash",
        tmdb_id="99999",
        info_hash="ABCDEF",
        identity_authority=IdentityAuthority.PROVIDER_RESOLVED,
        identity_confidence=82,
        identity_resolver_version="tmdb-v2",
    )

    resolved = await SyncLibraryStateRepository(cast(AsyncSession, object()))._media_item(  # pyright: ignore[reportPrivateUsage]
        synced_file,
        cast(MediaIdentityRepository, repository),
    )

    assert resolved is existing_item
    assert (existing_item.title, existing_item.year) == ("Ascendance of a Bookworm", 2019)
    assert repository.identity_write is not None
    assert repository.identity_write.title == "Incorrect provider title"
    assert repository.identity_write.year == 2024
    assert repository.identity_write.tmdb_id == "99999"
    assert repository.identity_write.authority is IdentityAuthority.PROVIDER_RESOLVED
    assert repository.identity_write.confidence == 82
    assert repository.identity_write.resolver_version == "tmdb-v2"
    assert repository.source_write is not None
    assert repository.source_write.source_title == "Ascendance of a Bookworm 01 JP BD Hi10"
    assert repository.source_write.info_hash == "ABCDEF"


@pytest.mark.asyncio
async def test_search_confirmed_authority_is_persisted_on_source_binding(tmp_path: Path) -> None:
    existing_item = MediaItem(
        id=10,
        content_kind="series",
        title="Kaiju No. 8",
        year=2024,
    )
    repository = CapturingIdentityRepository(existing_item)
    synced_file = SyncedStrmFile(
        path=tmp_path / "anime" / "Kaiju No. 8" / "Season 01" / "S01E01.strm",
        entry_id="entry-id",
        category="anime",
        title="Kaiju No. 8",
        source_title="Kaijuu 8-gou",
        year=2024,
        season_number=1,
        episode_number=1,
        provider="torrents",
        provider_item_id="42",
        provider_file_id="2",
        content_hash="content-hash",
        tmdb_id="207468",
        info_hash="abcdef",
        identity_authority=IdentityAuthority.SEARCH_CONFIRMED,
        identity_confidence=100,
    )

    _ = await SyncLibraryStateRepository(cast(AsyncSession, object()))._media_item(  # pyright: ignore[reportPrivateUsage]
        synced_file,
        cast(MediaIdentityRepository, repository),
    )

    assert repository.identity_write is not None
    assert repository.identity_write.authority is IdentityAuthority.SEARCH_CONFIRMED
    assert repository.source_write is not None
    assert repository.source_write.authority is IdentityAuthority.SEARCH_CONFIRMED
    assert repository.source_write.source_item_id == "42"
    assert repository.source_write.info_hash == "abcdef"
