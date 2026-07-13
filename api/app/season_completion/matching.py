from __future__ import annotations

import re

TITLE_TOKEN = re.compile(r"[a-z0-9]+")
SEASON_OR_EPISODE = re.compile(
    r"(?:^|[^a-z0-9])(?:s\d{1,2}(?:e\d{1,3})?|\d{1,2}e\d{1,3})(?=$|[^a-z0-9])"
)


def title_matches_show(show_title: str, candidate_title: str) -> bool:
    """Return whether a release label starts with the show title and season details."""
    show_tokens = _tokens(show_title)
    if not show_tokens:
        return False
    normalized_candidate = candidate_title.casefold()
    title_pattern = r"[^a-z0-9]+".join(re.escape(token) for token in show_tokens)
    title_match = re.match(rf"{title_pattern}(?=$|[^a-z0-9])", normalized_candidate)
    return (
        title_match is not None
        and SEASON_OR_EPISODE.search(normalized_candidate, title_match.end()) is not None
    )


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(TITLE_TOKEN.findall(value.casefold()))
