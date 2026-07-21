from pathlib import Path
from typing import ClassVar, cast

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.library_exclusion import BackingProviderItem
from app.library import removal_service
from app.library.removal import stage_library_prefix_removal
from app.library.removal_service import (
    TorBoxRemovalClientFactory,
    TorBoxRemovalConfig,
    remove_library_media,
)
from app.providers.torbox.client import TorBoxAPIError


@pytest.fixture(autouse=True)
def replace_stream_selection_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeStreamSelectionRepository.deleted_torrent_ids = []
    monkeypatch.setattr(
        removal_service,
        "StreamSelectionRepository",
        FakeStreamSelectionRepository,
    )


def test_staged_removal_can_be_restored(tmp_path: Path) -> None:
    target = _library_entry(tmp_path)

    staged = stage_library_prefix_removal(tmp_path, "shows/Show")

    assert target.exists() is False
    assert staged.removed_files == 1
    staged.restore()
    assert target.read_text(encoding="utf-8") == "playback\n"


def test_staged_removal_finalizes_quarantined_files(tmp_path: Path) -> None:
    target = _library_entry(tmp_path)

    staged = stage_library_prefix_removal(tmp_path, "shows/Show")
    outcome = staged.finalize()

    assert outcome.removed_files == 1
    assert target.exists() is False
    assert list((tmp_path / ".strmline").rglob("payload")) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_error", "expected_status"),
    [
        (TorBoxAPIError("item already absent", error_code="ITEM_NOT_FOUND"), "complete"),
        (httpx.ConnectError("provider unavailable"), "unconfirmed"),
    ],
)
async def test_provider_issue_keeps_local_removal_and_exclusion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider_error: Exception,
    expected_status: str,
) -> None:
    target = _library_entry(tmp_path)
    repository = FakeExclusionRepository()

    def repository_factory(_session: object) -> FakeExclusionRepository:
        return repository

    monkeypatch.setattr(removal_service, "LibraryExclusionRepository", repository_factory)

    class FailingClient:
        async def __aenter__(self) -> "FailingClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            _ = args

        async def delete_download(self, kind: str, item_id: str) -> None:
            _ = (kind, item_id)
            raise provider_error

    session = FakeSession()

    def client_factory(**kwargs: object) -> FailingClient:
        _ = kwargs
        return FailingClient()

    outcome = await remove_library_media(
        cast(AsyncSession, session),
        library_root=tmp_path,
        category="shows",
        title="Show",
        relative_prefix="shows/Show",
        backing_items=(BackingProviderItem(kind="torrents", item_id="1"),),
        torbox=TorBoxRemovalConfig("key", "https://torbox.invalid", 1.0),
        client_factory=cast(TorBoxRemovalClientFactory, client_factory),
    )

    assert target.exists() is False
    assert repository.added == ["shows/Show"]
    assert repository.removed_generated_files == ["shows/Show"]
    assert FakeStreamSelectionRepository.deleted_torrent_ids == [{"1"}]
    assert repository.removed == []
    assert session.rollbacks == 0
    assert outcome.removed_files == 1
    assert outcome.removed_torbox_items == 0
    assert outcome.torbox_removal_failed is (expected_status == "unconfirmed")
    assert list((tmp_path / ".strmline").rglob("payload")) == []


@pytest.mark.asyncio
async def test_item_failure_does_not_block_other_torbox_deletions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = _library_entry(tmp_path)
    repository = FakeExclusionRepository()

    def repository_factory(_session: object) -> FakeExclusionRepository:
        return repository

    monkeypatch.setattr(
        removal_service,
        "LibraryExclusionRepository",
        repository_factory,
    )

    class PartiallyFailingClient:
        async def __aenter__(self) -> "PartiallyFailingClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            _ = args

        async def delete_download(self, kind: str, item_id: str) -> None:
            _ = kind
            if item_id == "already-gone":
                raise TorBoxAPIError("item already absent")

    def client_factory(**kwargs: object) -> PartiallyFailingClient:
        _ = kwargs
        return PartiallyFailingClient()

    outcome = await remove_library_media(
        cast(AsyncSession, FakeSession()),
        library_root=tmp_path,
        category="shows",
        title="Show",
        relative_prefix="shows/Show",
        backing_items=(
            BackingProviderItem(kind="torrents", item_id="already-gone"),
            BackingProviderItem(kind="torrents", item_id="still-present"),
        ),
        torbox=TorBoxRemovalConfig("key", "https://torbox.invalid", 1.0),
        client_factory=cast(TorBoxRemovalClientFactory, client_factory),
    )

    assert outcome.removed_torbox_items == 1
    assert outcome.torbox_removal_failed is True


@pytest.mark.asyncio
async def test_database_failure_restores_staged_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = _library_entry(tmp_path)
    repository = FakeExclusionRepository()

    def repository_factory(_session: object) -> FakeExclusionRepository:
        return repository

    monkeypatch.setattr(removal_service, "LibraryExclusionRepository", repository_factory)
    session = FakeSession(fail_commit=2)

    with pytest.raises(RuntimeError, match="commit failed"):
        _ = await remove_library_media(
            cast(AsyncSession, session),
            library_root=tmp_path,
            category="shows",
            title="Show",
            relative_prefix="shows/Show",
            backing_items=(),
            torbox=None,
        )

    assert target.exists() is True
    assert session.rollbacks == 1


class FakeSession:
    def __init__(self, *, fail_commit: int | None = None) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.fail_commit = fail_commit

    async def commit(self) -> None:
        self.commits += 1
        if self.commits == self.fail_commit:
            raise RuntimeError("commit failed")

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeExclusionRepository:
    def __init__(self) -> None:
        self.added: list[str] = []
        self.removed: list[str] = []
        self.removed_generated_files: list[str] = []

    async def add(self, *, category: str, title: str, relative_prefix: str) -> None:
        _ = (category, title)
        self.added.append(relative_prefix)

    async def remove(self, relative_prefix: str) -> bool:
        self.removed.append(relative_prefix)
        return True

    async def remove_generated_files(self, relative_prefix: str) -> int:
        self.removed_generated_files.append(relative_prefix)
        return 1


class FakeStreamSelectionRepository:
    deleted_torrent_ids: ClassVar[list[set[str]]] = []

    def __init__(self, session: object) -> None:
        _ = session

    async def delete_for_torbox_items(self, torrent_ids: set[str]) -> int:
        self.deleted_torrent_ids.append(torrent_ids)
        return len(torrent_ids)


def _library_entry(root: Path) -> Path:
    target = root / "shows" / "Show" / "Season 01" / "Show - S01E01.strm"
    target.parent.mkdir(parents=True)
    _ = target.write_text("playback\n", encoding="utf-8")
    return target
