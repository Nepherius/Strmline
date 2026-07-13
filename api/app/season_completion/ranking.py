from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

SEASON_EPISODE = re.compile(r"(?i)s\d{1,2}e(?=\d{1,3}(?:\D|$))")
ALT_SEASON_EPISODE = re.compile(r"(?i)\d{1,2}x(?=\d{1,3}(?:\D|$))")
EPISODE_ONLY = re.compile(r"(?i)e(?=\d{1,3}(?:\D|$))")
SEPARATORS = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, order=True, slots=True)
class EpisodeRef:
    season: int
    episode: int


@dataclass(frozen=True, slots=True)
class CompletionCandidate:
    source_id: str
    info_hash: str | None
    title: str
    release_family: str | None
    episodes: frozenset[EpisodeRef]
    cached: bool
    action_url: str | None = None
    match_labels: tuple[str, ...] = ()


def release_family(filename: str | None) -> str | None:
    if not filename:
        return None
    match = (
        SEASON_EPISODE.search(filename)
        or ALT_SEASON_EPISODE.search(filename)
        or EPISODE_ONLY.search(filename)
    )
    if match is None:
        return None
    prefix = filename[: match.end()].casefold()
    normalized = SEPARATORS.sub(" ", prefix).strip()
    return normalized or None


def dominant_release_family(filenames: list[str]) -> str | None:
    families = [family for filename in filenames if (family := release_family(filename))]
    if not families:
        return None
    counts = Counter(families)
    return min(counts, key=lambda family: (-counts[family], family))


def choose_candidates(
    candidates: list[CompletionCandidate],
    *,
    missing: frozenset[EpisodeRef],
    dominant_family: str | None,
    allow_uncached: bool,
) -> tuple[CompletionCandidate, ...]:
    remaining = set(missing)
    available = [candidate for candidate in candidates if candidate.cached or allow_uncached]
    complete = [candidate for candidate in available if missing.issubset(candidate.episodes)]
    if complete:
        complete.sort(key=lambda candidate: _rank(candidate, remaining, dominant_family))
        return (complete[0],)
    selected: list[CompletionCandidate] = []

    while remaining:
        useful = [
            candidate for candidate in available if candidate.episodes.intersection(remaining)
        ]
        if not useful:
            break
        useful.sort(key=lambda candidate: _rank(candidate, remaining, dominant_family))
        chosen = useful[0]
        selected.append(chosen)
        remaining.difference_update(chosen.episodes)
        available = [
            candidate for candidate in available if candidate.source_id != chosen.source_id
        ]

    return tuple(selected)


def _rank(
    candidate: CompletionCandidate,
    remaining: set[EpisodeRef],
    dominant_family: str | None,
) -> tuple[int, int, int, str]:
    same_family = dominant_family is not None and candidate.release_family == dominant_family
    coverage = len(candidate.episodes.intersection(remaining))
    return (
        0 if candidate.cached else 1,
        0 if same_family else 1,
        -coverage,
        candidate.title.casefold(),
    )
