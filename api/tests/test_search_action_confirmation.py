from typing import cast

import pytest

from app.db.repositories.stream_selection import (
    StreamSelectionRecord,
    StreamSelectionRepository,
    StreamSelectionWrite,
)
from app.providers.aiostreams.client import AioStreamsClient, AioStreamsStream
from app.providers.torbox.client import TorBoxClient
from app.search.actions import (
    StreamActionError,
    StreamActionTarget,
    add_stream_to_torbox,
)
from app.search.stream_identity import stream_identity


class FakeAioStreamsClient:
    def __init__(self, stream: AioStreamsStream) -> None:
        self.stream = stream

    async def streams(self, *, media_type: str, media_id: str) -> tuple[AioStreamsStream, ...]:
        _ = (media_type, media_id)
        return (self.stream,)

    async def trigger_stream_url(self, url: str) -> None:
        _ = url


class FakeTorBoxClient:
    def __init__(self, downloads: list[dict[str, object]]) -> None:
        self.downloads = downloads

    async def list_downloads(
        self,
        kind: object,
        *,
        limit: int = 1000,
    ) -> list[dict[str, object]]:
        _ = (kind, limit)
        return self.downloads


class CapturingRepository:
    def __init__(self) -> None:
        self.writes: list[StreamSelectionWrite] = []

    async def upsert(self, write: StreamSelectionWrite) -> StreamSelectionRecord:
        self.writes.append(write)
        return StreamSelectionRecord(
            stream_key=write.stream_key,
            media_type=write.media_type,
            media_id=write.media_id,
            title=write.title,
            source_name=write.source_name,
            info_hash=write.info_hash,
            torbox_torrent_id=write.torbox_torrent_id,
            status=write.status,
        )


def _action_stream() -> AioStreamsStream:
    return AioStreamsStream(
        name="[TB⚡] StremThru Torz 1080p",
        title="Movie.1080p.WEB-DL.x264.mkv",
        description=None,
        url="https://example.invalid/add",
        info_hash=None,
        file_idx=None,
        behavior_hints={"filename": "Movie.1080p.WEB-DL.x264.mkv"},
        raw={},
    )


def _target(stream: AioStreamsStream) -> StreamActionTarget:
    media_id = "tt1234567"
    identity = stream_identity(stream, media_type="movie", media_id=media_id)
    return StreamActionTarget(
        media_type="movie",
        media_id=media_id,
        stream_key=identity.stream_key,
    )


@pytest.mark.asyncio
async def test_action_stream_matches_torrent_that_already_exists() -> None:
    stream = _action_stream()
    repository = CapturingRepository()
    torbox = FakeTorBoxClient(
        [
            {
                "id": 889,
                "name": "Movie.1080p.WEB-DL.x264.mkv",
                "hash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "files": [],
            }
        ]
    )

    outcome = await add_stream_to_torbox(
        aiostreams_client=cast(AioStreamsClient, FakeAioStreamsClient(stream)),
        torbox_client=cast(TorBoxClient, torbox),
        repository=cast(StreamSelectionRepository, repository),
        target=_target(stream),
    )

    assert outcome.torbox_torrent_id == "889"
    assert repository.writes[0].info_hash == "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


@pytest.mark.asyncio
async def test_action_stream_is_rejected_when_torbox_cannot_confirm_it() -> None:
    stream = _action_stream()
    repository = CapturingRepository()

    with pytest.raises(StreamActionError, match="TorBox did not confirm"):
        _ = await add_stream_to_torbox(
            aiostreams_client=cast(AioStreamsClient, FakeAioStreamsClient(stream)),
            torbox_client=cast(TorBoxClient, FakeTorBoxClient([])),
            repository=cast(StreamSelectionRepository, repository),
            target=_target(stream),
        )

    assert repository.writes == []
