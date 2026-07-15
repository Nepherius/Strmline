from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LibraryEntry, PlaybackAttempt, TorBoxItem, TorBoxStoredFile
from app.db.repositories.resolver import PlaybackResolverRepository, ResolverLookupError
from app.providers.torbox.client import TorBoxAPIError
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
        torbox_file_id=2,
        category="movies",
    )
    stored_file = TorBoxStoredFile(
        id=2,
        torbox_item_id=1,
        external_id="2",
        file_name="Movie.2024.mkv",
        path="Movie/Movie.2024.mkv",
        mime_type="video/x-matroska",
        size=1_000,
    )
    stored_file.torbox_item = TorBoxItem(
        id=1, kind="torrents", external_id="1", name="Movie", raw_payload={}
    )
    library_entry.torbox_file = stored_file
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


@pytest.mark.asyncio
async def test_resolver_repository_readds_missing_virtual_torrent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.db.repositories.resolver.PLAYBACK_RECOVERY_INTERVAL_SECONDS",
        0,
    )
    library_entry = LibraryEntry(
        id=42,
        opaque_id="permanent-entry",
        media_item_id=1,
        torbox_file_id=None,
        category="movies",
        info_hash="abc123",
        source_kind="torrents",
        source_item_id="old-item",
        source_item_name="Movie",
        source_file_id="old-file",
        source_file_name="Movie.2024.mkv",
        source_file_path="Movie/Movie.2024.mkv",
        source_file_mime_type="video/x-matroska",
        source_file_size=1_000,
    )
    library_entry.torbox_file = None
    client = FakePlaybackClient()
    session = FakeSession([FakeResult(scalar=library_entry)])

    target = await _repository(session).resolve_torbox_target(
        entry_id="permanent-entry",
        api_key="api-key",
        torbox_base_url="https://api.torbox.app/v1/api",
        torbox_client=client,
    )

    assert target.target_url == "https://cdn.example.test/Movie.2024.mkv"
    assert client.created_magnets == ["magnet:?xt=urn:btih:abc123"]
    assert client.requested_ids == [("old-item", "old-file"), ("99", "7")]
    assert _playback_attempt(session).status == "redirect"


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


class FakePlaybackClient:
    def __init__(self) -> None:
        self.created_magnets: list[str] = []
        self.requested_ids: list[tuple[str, str]] = []

    async def request_download_link(self, torbox_file: TorBoxFile) -> str:
        self.requested_ids.append((torbox_file.item_id, torbox_file.file_id))
        if torbox_file.item_id == "old-item":
            raise TorBoxAPIError("missing")
        return "https://cdn.example.test/Movie.2024.mkv"

    async def find_torrent_by_hash(self, info_hash: str) -> dict[str, object] | None:
        _ = info_hash
        return None

    async def create_torrent(
        self,
        *,
        magnet: str,
        name: str | None = None,
        add_only_if_cached: bool = True,
    ) -> dict[str, object]:
        _ = name
        _ = add_only_if_cached
        self.created_magnets.append(magnet)
        return {"torrent_id": 99}

    async def get_download(self, kind: str, item_id: str) -> dict[str, object] | None:
        _ = kind
        _ = item_id
        return {
            "id": 99,
            "cached": True,
            "download_finished": True,
            "name": "Movie",
            "files": [
                {
                    "id": 7,
                    "short_name": "Movie.2024.mkv",
                    "name": "Movie/Movie.2024.mkv",
                    "mimetype": "video/x-matroska",
                    "size": 1_000,
                }
            ],
        }
