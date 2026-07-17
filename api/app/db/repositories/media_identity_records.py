from __future__ import annotations

from dataclasses import dataclass

from app.domain.media_identity import (
    ContentKind,
    IdentityAuthority,
    LibraryCategory,
    ProviderMediaKind,
)


@dataclass(frozen=True, slots=True)
class PersistedMediaIdentity:
    media_item_id: int
    content_kind: str
    title: str
    year: int | None
    tmdb_id: str | None
    provider_media_kind: str | None
    authority: str
    authoritative: bool
    confidence: int | None
    resolver_version: str | None
    library_category: str | None = None
    poster_path: str | None = None


@dataclass(frozen=True, slots=True)
class SourceIdentityBinding:
    source_kind: str
    source_item_id: str | None
    info_hash: str | None
    identity: PersistedMediaIdentity


@dataclass(frozen=True, slots=True)
class AliasIdentityBinding:
    normalized_alias: str
    identity: PersistedMediaIdentity


@dataclass(frozen=True, slots=True)
class MediaIdentityWrite:
    content_kind: ContentKind
    library_category: LibraryCategory
    title: str
    year: int | None
    tmdb_id: str | None
    provider_media_kind: ProviderMediaKind
    authority: IdentityAuthority
    confidence: int | None
    resolver_version: str | None
    poster_path: str | None = None


@dataclass(frozen=True, slots=True)
class SourceBindingWrite:
    source_kind: str
    source_item_id: str | None
    info_hash: str | None
    source_title: str
    authority: IdentityAuthority
    confidence: int | None
    resolver_version: str | None
