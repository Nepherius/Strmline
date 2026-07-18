from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MediaExternalIdentity, MediaItem, SourceMediaBinding
from app.db.repositories import media_identity as identity_module
from app.db.repositories.media_identity import MediaIdentityRepository, MediaIdentityWrite
from app.domain.media_identity import (
    ContentKind,
    IdentityAuthority,
    ProviderMediaKind,
)


class FakeResult:
    def __init__(
        self,
        *,
        scalar: object | None = None,
        rows: list[tuple[object, ...]] | None = None,
    ) -> None:
        self._scalar = scalar
        self._rows = rows or []

    def scalar_one_or_none(self) -> object | None:
        return self._scalar

    def all(self) -> list[tuple[object, ...]]:
        return self._rows


class FakeSession:
    def __init__(self, results: list[FakeResult]) -> None:
        self.results = results
        self.added: list[object] = []
        self.flushes = 0

    async def execute(self, statement: object) -> FakeResult:
        _ = statement
        return self.results.pop(0)

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flushes += 1


def _write(
    *,
    authority: IdentityAuthority = IdentityAuthority.PROVIDER_RESOLVED,
    title: str = "Kaiju No. 8",
    year: int | None = 2024,
    poster_path: str | None = "/kaiju.jpg",
) -> MediaIdentityWrite:
    return MediaIdentityWrite(
        content_kind=ContentKind.SERIES,
        library_category="anime",
        title=title,
        year=year,
        tmdb_id="207468",
        provider_media_kind=ProviderMediaKind.TV,
        authority=authority,
        confidence=100 if authority.authoritative else 80,
        resolver_version="test-v1",
        poster_path=poster_path,
    )


def test_authoritative_identity_is_immutable_during_provider_sync() -> None:
    media_item = MediaItem(
        id=1,
        content_kind="series",
        library_category="anime",
        title="Kaiju No. 8",
        year=2024,
        poster_path="/canonical.jpg",
    )
    external_identity = MediaExternalIdentity(
        media_item_id=1,
        provider="tmdb",
        provider_media_kind="tv",
        external_id="207468",
        authority=IdentityAuthority.SEARCH_CONFIRMED.value,
        authoritative=True,
        confidence=100,
    )

    identity_module.MediaIdentityRepository._apply_stronger_identity(  # pyright: ignore[reportPrivateUsage]
        media_item,
        external_identity,
        replace(_write(), title="Wrong title", year=2030, poster_path="/wrong.jpg"),
    )

    assert (media_item.title, media_item.year) == ("Kaiju No. 8", 2024)
    assert media_item.poster_path == "/canonical.jpg"
    assert external_identity.external_id == "207468"
    assert external_identity.authority == IdentityAuthority.SEARCH_CONFIRMED.value


def test_authoritative_identity_fills_only_missing_metadata_during_sync() -> None:
    media_item = MediaItem(
        id=1,
        content_kind="series",
        library_category="anime",
        title="Ascendance of a Bookworm",
        year=None,
        poster_path=None,
    )
    external_identity = MediaExternalIdentity(
        media_item_id=1,
        provider="tmdb",
        provider_media_kind="tv",
        external_id="91768",
        authority=IdentityAuthority.MANUAL.value,
        authoritative=True,
        confidence=100,
    )

    identity_module.MediaIdentityRepository._apply_stronger_identity(  # pyright: ignore[reportPrivateUsage]
        media_item,
        external_identity,
        replace(
            _write(),
            title="Provider title must not replace canonical title",
            year=2019,
            poster_path="/bookworm.jpg",
        ),
    )

    assert media_item.title == "Ascendance of a Bookworm"
    assert media_item.year == 2019
    assert media_item.poster_path == "/bookworm.jpg"
    assert external_identity.external_id == "91768"
    assert external_identity.authority == IdentityAuthority.MANUAL.value


def test_search_confirmation_promotes_a_non_authoritative_match() -> None:
    media_item = MediaItem(
        id=1,
        content_kind="series",
        library_category="anime",
        title="Kaijuu 8-gou",
        year=None,
    )
    external_identity = MediaExternalIdentity(
        media_item_id=1,
        provider="tmdb",
        provider_media_kind="tv",
        external_id="207468",
        authority=IdentityAuthority.PROVIDER_RESOLVED.value,
        authoritative=False,
        confidence=60,
    )

    identity_module.MediaIdentityRepository._apply_stronger_identity(  # pyright: ignore[reportPrivateUsage]
        media_item,
        external_identity,
        _write(authority=IdentityAuthority.SEARCH_CONFIRMED),
    )

    assert (media_item.title, media_item.year) == ("Kaiju No. 8", 2024)
    assert external_identity.authoritative is True
    assert external_identity.authority == IdentityAuthority.SEARCH_CONFIRMED.value


@pytest.mark.parametrize(
    ("authority", "expected"),
    [
        (IdentityAuthority.MANUAL, 50),
        (IdentityAuthority.SEARCH_CONFIRMED, 40),
        (IdentityAuthority.MIGRATED, 30),
        (IdentityAuthority.PROVIDER_RESOLVED, 20),
        (IdentityAuthority.FALLBACK, 0),
    ],
)
def test_identity_authority_precedence_is_centralized(
    authority: IdentityAuthority,
    expected: int,
) -> None:
    assert identity_module.identity_authority_priority(authority) == expected


def test_persisted_identity_prefers_source_provenance() -> None:
    media_item = MediaItem(
        id=4,
        content_kind="series",
        library_category="anime",
        title="Ascendance of a Bookworm",
        year=2019,
    )
    external_identity = MediaExternalIdentity(
        media_item_id=4,
        provider="tmdb",
        provider_media_kind="tv",
        external_id="91768",
        authority=IdentityAuthority.MIGRATED.value,
        authoritative=False,
        confidence=None,
        resolver_version="legacy-v1",
    )
    source_binding = SourceMediaBinding(
        media_item_id=4,
        source_kind="torrents",
        source_item_id="42",
        info_hash=None,
        authority=IdentityAuthority.MANUAL.value,
        authoritative=True,
        confidence=100,
        resolver_version=None,
    )

    persisted = identity_module._persisted_identity(  # pyright: ignore[reportPrivateUsage]
        media_item,
        external_identity,
        source_binding,
    )

    assert persisted.tmdb_id == "91768"
    assert persisted.library_category == "anime"
    assert persisted.authority == IdentityAuthority.MANUAL.value
    assert persisted.authoritative is True
    assert persisted.confidence == 100


@pytest.mark.asyncio
async def test_repository_reads_source_and_alias_bindings() -> None:
    media_item = MediaItem(
        id=7,
        content_kind="series",
        library_category="anime",
        title="Kaiju No. 8",
        year=2024,
    )
    external_identity = MediaExternalIdentity(
        media_item_id=7,
        provider="tmdb",
        provider_media_kind="tv",
        external_id="207468",
        authority=IdentityAuthority.SEARCH_CONFIRMED.value,
        authoritative=True,
        confidence=100,
    )
    source = SourceMediaBinding(
        media_item_id=7,
        source_kind="torrents",
        source_item_id="42",
        info_hash=None,
        authority=IdentityAuthority.SEARCH_CONFIRMED.value,
        authoritative=True,
        confidence=100,
    )
    alias = identity_module.MediaAlias(
        media_item_id=7,
        content_kind="series",
        alias="Kaijuu 8-gou",
        normalized_alias="kaijuu 8 gou",
        source=IdentityAuthority.SEARCH_CONFIRMED.value,
    )
    session = FakeSession(
        [
            FakeResult(rows=[(source, media_item, external_identity)]),
            FakeResult(rows=[(alias, media_item, external_identity)]),
        ]
    )
    repository = MediaIdentityRepository(cast(AsyncSession, session))

    source_records = await repository.source_bindings()
    alias_records = await repository.alias_bindings()

    assert source_records[0].source_item_id == "42"
    assert source_records[0].identity.tmdb_id == "207468"
    assert source_records[0].identity.authoritative is True
    assert alias_records[0].normalized_alias == "kaijuu 8 gou"
    assert alias_records[0].identity.media_item_id == 7


@pytest.mark.asyncio
async def test_repository_reuses_authoritative_external_identity() -> None:
    media_item = MediaItem(
        id=7,
        content_kind="series",
        library_category="anime",
        title="Kaiju No. 8",
        year=2024,
    )
    external_identity = MediaExternalIdentity(
        media_item_id=7,
        provider="tmdb",
        provider_media_kind="tv",
        external_id="207468",
        authority=IdentityAuthority.SEARCH_CONFIRMED.value,
        authoritative=True,
        confidence=100,
    )
    external_identity.media_item = media_item
    session = FakeSession([FakeResult(scalar=external_identity), FakeResult(scalar=None)])
    repository = identity_module.MediaIdentityRepository(cast(AsyncSession, session))

    resolved = await repository.ensure_media(replace(_write(), title="Wrong", year=2030))

    assert resolved is media_item
    assert (media_item.title, media_item.year) == ("Kaiju No. 8", 2024)
    assert len(session.added) == 1
