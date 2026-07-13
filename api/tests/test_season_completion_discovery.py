import pytest

from app.providers.aiostreams.client import AioStreamsStream
from app.season_completion.discovery import discover_candidates, group_stream_candidates
from app.season_completion.ranking import EpisodeRef


def test_group_stream_candidates_recognizes_pack_by_shared_hash() -> None:
    stream_one = _stream(HASH, "Show.Group.S01E01.mkv")
    stream_two = _stream(HASH.upper(), "Show.Group.S01E02.mkv")

    candidates = group_stream_candidates(
        {
            EpisodeRef(1, 1): (stream_one,),
            EpisodeRef(1, 2): (stream_two,),
        },
        cached_by_hash={HASH: True},
    )

    assert len(candidates) == 1
    assert candidates[0].info_hash == HASH
    assert candidates[0].episodes == frozenset({EpisodeRef(1, 1), EpisodeRef(1, 2)})
    assert candidates[0].cached is True
    assert candidates[0].release_family == "show group s01e"


def test_group_stream_candidates_uses_provider_folder_label_for_title_validation() -> None:
    stream = AioStreamsStream(
        name="[TB\u26a1] AnimeTosho 1080p",
        title=None,
        description="\U0001f4c1 Ascendance Of A Bookworm S01 \u2022 E01\n\U0001f3a5 BluRay",
        url="https://example.invalid/torbox-action",
        info_hash=None,
        file_idx=None,
        behavior_hints={"filename": "[sam] Ascendance of a Bookworm - 01.mkv"},
        raw={},
    )

    candidates = group_stream_candidates(
        {EpisodeRef(1, 1): (stream,)},
        cached_by_hash={},
    )

    assert candidates[0].title == "[sam] Ascendance of a Bookworm - 01.mkv"
    assert candidates[0].match_labels == (
        "[sam] Ascendance of a Bookworm - 01.mkv",
        "Ascendance Of A Bookworm S01 \u2022 E01",
    )


def test_group_stream_candidates_groups_cached_action_pack_across_episodes() -> None:
    streams_by_episode = {
        EpisodeRef(1, episode): (_action_pack_stream(episode),) for episode in (1, 2, 3)
    }

    candidates = group_stream_candidates(streams_by_episode, cached_by_hash={})

    assert len(candidates) == 1
    assert candidates[0].episodes == frozenset(
        {EpisodeRef(1, 1), EpisodeRef(1, 2), EpisodeRef(1, 3)}
    )


def test_group_stream_candidates_keeps_individual_cached_actions_separate() -> None:
    streams_by_episode = {
        EpisodeRef(1, episode): (_action_pack_stream(episode, total_size="1 GB"),)
        for episode in (1, 2)
    }

    candidates = group_stream_candidates(streams_by_episode, cached_by_hash={})

    assert len(candidates) == 2


def test_group_stream_candidates_ignores_results_without_info_hash() -> None:
    direct = AioStreamsStream(
        name="Direct",
        title="Show.S01E01.mkv",
        description=None,
        url="https://example.invalid/play",
        info_hash=None,
        file_idx=None,
        behavior_hints={},
        raw={},
    )

    assert (
        group_stream_candidates(
            {EpisodeRef(1, 1): (direct,)},
            cached_by_hash={},
        )
        == []
    )


def test_group_stream_candidates_keeps_cached_torbox_action_streams_without_hash() -> None:
    action = AioStreamsStream(
        name="[TB⚡] Cached",
        title="Show.S01E01.mkv",
        description=None,
        url="https://example.invalid/torbox-action",
        info_hash=None,
        file_idx=None,
        behavior_hints={"filename": "Show.S01E01.mkv"},
        raw={},
    )

    candidates = group_stream_candidates(
        {EpisodeRef(1, 1): (action,)},
        cached_by_hash={},
    )

    assert len(candidates) == 1
    assert candidates[0].info_hash is None
    assert candidates[0].action_url == "https://example.invalid/torbox-action"
    assert candidates[0].cached is True


def test_group_stream_candidates_ignores_uncached_torbox_action_streams_without_hash() -> None:
    action = AioStreamsStream(
        name="[TB] StreamThru Torz",
        title="Show.S01E01.mkv",
        description=None,
        url="https://example.invalid/torbox-action",
        info_hash=None,
        file_idx=None,
        behavior_hints={"filename": "Show.S01E01.mkv"},
        raw={},
    )

    assert group_stream_candidates({EpisodeRef(1, 1): (action,)}, cached_by_hash={}) == []


@pytest.mark.asyncio
async def test_discover_candidates_checks_cache_for_unique_hashes() -> None:
    class FakeAioStreams:
        async def streams(
            self,
            *,
            media_type: str,
            media_id: str,
        ) -> tuple[AioStreamsStream, ...]:
            assert media_type == "series"
            episode = media_id.rsplit(":", maxsplit=1)[-1]
            return (_stream(HASH.upper(), f"Show.S01E{episode}.mkv"),)

    class FakeTorBox:
        async def check_cached(self, hashes: list[str]) -> dict[str, bool]:
            assert hashes == [HASH]
            return {HASH: True}

    candidates = await discover_candidates(
        aiostreams_client=FakeAioStreams(),
        torbox_client=FakeTorBox(),
        imdb_id="tt1234567",
        missing=frozenset({EpisodeRef(1, 2), EpisodeRef(1, 3)}),
    )

    assert candidates[0].episodes == frozenset({EpisodeRef(1, 2), EpisodeRef(1, 3)})


def _stream(info_hash: str, filename: str) -> AioStreamsStream:
    return AioStreamsStream(
        name="[TB]",
        title=filename,
        description=None,
        url=None,
        info_hash=info_hash,
        file_idx=0,
        behavior_hints={"filename": filename},
        raw={},
    )


def _action_pack_stream(episode: int, *, total_size: str = "22 GB") -> AioStreamsStream:
    return AioStreamsStream(
        name="[TB\u26a1] AnimeTosho 1080p",
        title=None,
        description=(
            f"\U0001f4c1 Ascendance Of A Bookworm S01 \u2022 E{episode:02d}\n"
            f"\U0001f4e6 1 GB / {total_size}"
        ),
        url=f"https://example.invalid/torbox-action-{episode}",
        info_hash=None,
        file_idx=None,
        behavior_hints={
            "bingeGroup": "com.aiostreams.example|1080p|BluRay|release",
            "filename": f"Ascendance.of.a.Bookworm.S01E{episode:02d}.mkv",
            "videoSize": 1024**3,
        },
        raw={},
    )


HASH = "4fb46a63360b938999b72a73e2c19f2231f8a5c3"
