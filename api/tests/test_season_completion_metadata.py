from datetime import date

from app.season_completion.metadata import regular_released_episodes, season_numbers
from app.season_completion.ranking import EpisodeRef


def test_season_numbers_excludes_specials() -> None:
    payload = {
        "seasons": [
            {"season_number": 0},
            {"season_number": 1},
            {"season_number": 2},
            {"season_number": "3"},
        ]
    }

    assert season_numbers(payload) == (1, 2)


def test_regular_released_episodes_excludes_unaired_and_invalid_entries() -> None:
    payload = {
        "episodes": [
            {"season_number": 1, "episode_number": 1, "air_date": "2026-07-01"},
            {"season_number": 1, "episode_number": 2, "air_date": "2026-07-13"},
            {"season_number": 1, "episode_number": 3, "air_date": None},
            {"season_number": 0, "episode_number": 4, "air_date": "2026-01-01"},
        ]
    }

    assert regular_released_episodes(payload, today=date(2026, 7, 12)) == frozenset(
        {EpisodeRef(1, 1)}
    )
