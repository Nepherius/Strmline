from __future__ import annotations

from datetime import date
from typing import Any, cast

from app.season_completion.ranking import EpisodeRef


def season_numbers(payload: dict[str, Any]) -> tuple[int, ...]:
    raw_seasons = payload.get("seasons")
    if not isinstance(raw_seasons, list):
        return ()
    numbers: set[int] = set()
    for raw in cast(list[object], raw_seasons):
        if not isinstance(raw, dict):
            continue
        season_data = cast(dict[str, Any], raw)
        number = season_data.get("season_number")
        if isinstance(number, int) and not isinstance(number, bool) and number > 0:
            numbers.add(number)
    return tuple(sorted(numbers))


def regular_released_episodes(
    payload: dict[str, Any],
    *,
    today: date,
) -> frozenset[EpisodeRef]:
    raw_episodes = payload.get("episodes")
    if not isinstance(raw_episodes, list):
        return frozenset()
    episodes: set[EpisodeRef] = set()
    for raw in cast(list[object], raw_episodes):
        if not isinstance(raw, dict):
            continue
        episode_data = cast(dict[str, Any], raw)
        season = episode_data.get("season_number")
        episode = episode_data.get("episode_number")
        air_date = _date_value(episode_data.get("air_date"))
        if (
            isinstance(season, int)
            and not isinstance(season, bool)
            and season > 0
            and isinstance(episode, int)
            and not isinstance(episode, bool)
            and episode > 0
            and air_date is not None
            and air_date <= today
        ):
            episodes.add(EpisodeRef(season, episode))
    return frozenset(episodes)


def imdb_id(payload: dict[str, Any]) -> str | None:
    value = payload.get("imdb_id")
    if isinstance(value, str) and value.startswith("tt") and value[2:].isdigit():
        return value
    return None


def _date_value(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
