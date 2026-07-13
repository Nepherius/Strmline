from app.season_completion.ranking import (
    CompletionCandidate,
    EpisodeRef,
    choose_candidates,
    dominant_release_family,
    release_family,
)


def test_release_family_uses_prefix_through_episode_marker() -> None:
    assert (
        release_family("From.Gal.2010.Saxy-UHD.S01E02.2160p.mkv") == "from gal 2010 saxy uhd s01e"
    )


def test_release_family_supports_unconventional_episode_prefix() -> None:
    assert release_family("from.gal,2010.saxy-uhd01e02.mkv") == "from gal 2010 saxy uhd01e"


def test_dominant_release_family_uses_most_common_family() -> None:
    assert (
        dominant_release_family(
            [
                "Show.Group.S01E01.mkv",
                "Show.Group.S01E02.mkv",
                "Show.Other.S01E03.mkv",
            ]
        )
        == "show group s01e"
    )


def test_complete_cached_pack_prevents_combining_pack_and_individual_episodes() -> None:
    missing = frozenset({EpisodeRef(1, 4), EpisodeRef(1, 5), EpisodeRef(1, 6)})
    same_family = _candidate(
        "same",
        family="show group s01e",
        episodes={EpisodeRef(1, 4)},
        cached=True,
    )
    pack = _candidate(
        "pack",
        family="show other s01e",
        episodes=set(missing),
        cached=True,
    )

    selected = choose_candidates(
        [pack, same_family],
        missing=missing,
        dominant_family="show group s01e",
        allow_uncached=False,
    )

    assert selected == (pack,)


def test_pack_is_selected_once_for_every_episode_it_covers() -> None:
    missing = frozenset({EpisodeRef(1, 4), EpisodeRef(1, 5), EpisodeRef(1, 6)})
    pack = _candidate("pack", family=None, episodes=set(missing), cached=True)

    selected = choose_candidates(
        [pack],
        missing=missing,
        dominant_family=None,
        allow_uncached=False,
    )

    assert selected == (pack,)


def test_uncached_candidates_require_opt_in_and_follow_cached_candidates() -> None:
    missing = frozenset({EpisodeRef(1, 4), EpisodeRef(1, 5)})
    cached = _candidate(
        "cached",
        family=None,
        episodes={EpisodeRef(1, 4)},
        cached=True,
    )
    uncached = _candidate(
        "uncached",
        family="show group s01e",
        episodes={EpisodeRef(1, 5)},
        cached=False,
    )

    assert choose_candidates(
        [uncached, cached],
        missing=missing,
        dominant_family="show group s01e",
        allow_uncached=False,
    ) == (cached,)
    assert choose_candidates(
        [uncached, cached],
        missing=missing,
        dominant_family="show group s01e",
        allow_uncached=True,
    ) == (cached, uncached)


def _candidate(
    info_hash: str,
    *,
    family: str | None,
    episodes: set[EpisodeRef],
    cached: bool,
) -> CompletionCandidate:
    return CompletionCandidate(
        source_id=f"hash:{info_hash}",
        info_hash=info_hash,
        title=info_hash,
        release_family=family,
        episodes=frozenset(episodes),
        cached=cached,
    )
