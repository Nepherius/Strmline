from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, cast

LibraryCategory = Literal["movies", "shows", "anime"]


class ContentKind(StrEnum):
    MOVIE = "movie"
    SERIES = "series"


class ProviderMediaKind(StrEnum):
    MOVIE = "movie"
    TV = "tv"


class IdentityAuthority(StrEnum):
    MANUAL = "manual"
    SEARCH_CONFIRMED = "search_confirmed"
    PROVIDER_RESOLVED = "provider_resolved"
    MIGRATED = "migrated"
    FALLBACK = "fallback"

    @property
    def authoritative(self) -> bool:
        return self in {self.MANUAL, self.SEARCH_CONFIRMED}


class ResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    NO_MATCH = "no_match"
    PROVIDER_ERROR = "provider_error"


def identity_authority_priority(authority: IdentityAuthority) -> int:
    return {
        IdentityAuthority.MANUAL: 50,
        IdentityAuthority.SEARCH_CONFIRMED: 40,
        IdentityAuthority.MIGRATED: 30,
        IdentityAuthority.PROVIDER_RESOLVED: 20,
        IdentityAuthority.FALLBACK: 0,
    }[authority]


@dataclass(frozen=True, slots=True)
class ExternalMediaIdentity:
    provider: str
    provider_kind: ProviderMediaKind
    external_id: str

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("Identity provider is required.")
        if not self.external_id.strip():
            raise ValueError("External identity is required.")


def content_kind_for_category(category: LibraryCategory | str) -> ContentKind:
    parsed = parse_library_category(category)
    return ContentKind.MOVIE if parsed == "movies" else ContentKind.SERIES


def parse_library_category(category: str) -> LibraryCategory:
    if category in {"movies", "shows", "anime"}:
        return cast(LibraryCategory, category)
    raise ValueError(f"Invalid library category: {category}")


def provider_kind_for_content(content_kind: ContentKind | str) -> ProviderMediaKind:
    parsed = ContentKind(content_kind)
    return ProviderMediaKind.MOVIE if parsed is ContentKind.MOVIE else ProviderMediaKind.TV


def provider_kind_for_search(media_type: str) -> ProviderMediaKind:
    if media_type == "movie":
        return ProviderMediaKind.MOVIE
    if media_type == "series":
        return ProviderMediaKind.TV
    raise ValueError(f"Invalid search media type: {media_type}")


def content_kind_for_provider(provider_kind: ProviderMediaKind | str) -> ContentKind:
    parsed = ProviderMediaKind(provider_kind)
    return ContentKind.MOVIE if parsed is ProviderMediaKind.MOVIE else ContentKind.SERIES


def search_media_type_for_category(category: LibraryCategory | str) -> str:
    return "movie" if parse_library_category(category) == "movies" else "series"
