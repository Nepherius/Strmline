from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LibraryEntry, PlaybackAttempt
from app.db.repositories.resolver import PlaybackResolverRepository, ResolverLookupError
from app.providers.torbox.files import TorBoxFile
from app.resolver.manifest import resolver_entry_id


class FakeResult:
    def __init__(self, scalar: object | None = None) -> None:
        self._scalar = scalar

    def scalar_one_or_none(self) -> object | None:
        return self._scalar


class FakeSession:
    def __init__(self, results: list[FakeResult]) -> None:
        self._results = results
        self.added: list[object] = []
        self.committed = False

    async def execute(self, statement: object) -> FakeResult:
        _ = statement
        return self._results.pop(0)

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def commit(self) -> None:
        self.committed = True


@pytest.mark.asyncio
async def test_resolver_repository_validates_saved_tokens() -> None:
    session = FakeSession([FakeResult(scalar=1)])

    assert await _repository(session).resolver_token_is_valid("resolver-token") is True


@pytest.mark.asyncio
async def test_resolver_repository_builds_torbox_target_and_records_attempt() -> None:
    entry_id = resolver_entry_id(_torbox_file())
    library_entry = LibraryEntry(
        id=42,
        opaque_id=entry_id,
        media_item_id=1,
        category="movies",
        provider="torbox",
        provider_item_id="1",
        provider_file_id="2",
    )
    session = FakeSession([FakeResult(scalar=library_entry)])

    target = await _repository(session).resolve_torbox_target(
        entry_id=entry_id,
        api_key="api-key",
        torbox_base_url="https://api.torbox.app/v1/api",
    )

    assert target.target_url == (
        "https://api.torbox.app/v1/api/torrents/requestdl?"
        "token=api-key&torrent_id=1&file_id=2&redirect=true"
    )
    attempt = _playback_attempt(session)
    assert attempt.library_entry_id == 42
    assert attempt.entry_opaque_id == entry_id
    assert attempt.status == "redirect"
    assert attempt.failure_reason is None


@pytest.mark.asyncio
async def test_resolver_repository_records_missing_entry_without_final_url() -> None:
    session = FakeSession([FakeResult(scalar=None)])

    with pytest.raises(ResolverLookupError):
        _ = await _repository(session).resolve_torbox_target(
            entry_id="missing-entry",
            api_key="api-key",
            torbox_base_url="https://api.torbox.app/v1/api",
        )

    attempt = _playback_attempt(session)
    assert attempt.library_entry_id is None
    assert attempt.entry_opaque_id == "missing-entry"
    assert attempt.status == "not_found"
    assert attempt.failure_reason == "library_entry_not_found"
    assert "api-key" not in repr(attempt)


def _repository(session: FakeSession) -> PlaybackResolverRepository:
    return PlaybackResolverRepository(cast(AsyncSession, session))


def _playback_attempt(session: FakeSession) -> PlaybackAttempt:
    return next(item for item in session.added if isinstance(item, PlaybackAttempt))


def _torbox_file() -> TorBoxFile:
    return TorBoxFile(
        kind="torrents",
        item_id="1",
        file_id="2",
        folder_name="Movie",
        file_name="Movie.2024.mkv",
        path="Movie/Movie.2024.mkv",
        mime_type="video/x-matroska",
        size=1_000,
    )
