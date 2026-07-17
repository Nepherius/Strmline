from pathlib import Path
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.library_exclusion import BackingProviderItem
from app.library import removal_service
from app.library.removal import stage_library_prefix_removal
from app.library.removal_service import (
    LibraryRemovalProviderError,
    TorBoxRemovalClientFactory,
    TorBoxRemovalConfig,
    remove_library_media,
)
from app.providers.torbox.client import TorBoxAPIError


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
async def test_provider_failure_restores_files_and_removes_exclusion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
            raise TorBoxAPIError("provider unavailable")

    session = FakeSession()

    def client_factory(**kwargs: object) -> FailingClient:
        _ = kwargs
        return FailingClient()

    with pytest.raises(LibraryRemovalProviderError):
        _ = await remove_library_media(
            cast(AsyncSession, session),
            library_root=tmp_path,
            category="shows",
            title="Show",
            relative_prefix="shows/Show",
            backing_items=(BackingProviderItem(kind="torrents", item_id="1"),),
            torbox=TorBoxRemovalConfig("key", "https://torbox.invalid", 1.0),
            client_factory=cast(TorBoxRemovalClientFactory, client_factory),
        )

    assert target.exists() is True
    assert repository.added == ["shows/Show"]
    assert repository.removed == ["shows/Show"]
    assert session.rollbacks == 1


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

    async def add(self, *, category: str, title: str, relative_prefix: str) -> None:
        _ = (category, title)
        self.added.append(relative_prefix)

    async def remove(self, relative_prefix: str) -> bool:
        self.removed.append(relative_prefix)
        return True


def _library_entry(root: Path) -> Path:
    target = root / "shows" / "Show" / "Season 01" / "Show - S01E01.strm"
    target.parent.mkdir(parents=True)
    _ = target.write_text("playback\n", encoding="utf-8")
    return target
