from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

LibraryCategory = Literal["movies", "shows", "anime"]


@dataclass(frozen=True, slots=True)
class LibraryEntry:
    category: LibraryCategory
    title: str
    resolver_url: str
    year: int | None = None
    season_number: int | None = None
    episode_number: int | None = None

    def __post_init__(self) -> None:
        if not self.title.strip():
            msg = "Library entry title is required."
            raise ValueError(msg)
        if not self.resolver_url.strip():
            msg = "Library entry resolver URL is required."
            raise ValueError(msg)
        if self.category == "movies":
            return
        if self.category == "anime" and self.season_number is None and self.episode_number is None:
            return
        if self.season_number is None or self.episode_number is None:
            msg = "Series entries require season and episode numbers."
            raise ValueError(msg)
        if self.season_number < 0 or self.episode_number < 0:
            msg = "Season and episode numbers cannot be negative."
            raise ValueError(msg)
