from typing import cast

import pytest

from app.db.repositories.media_identity import AliasIdentityBinding, PersistedMediaIdentity
from app.domain.media_identity import IdentityAuthority
from app.sync import identity_inputs
from app.sync.media_identity import MediaIdentity, MediaIdentityResolver


def test_authoritative_alias_wins_over_duplicate_fallback_media() -> None:
    bindings = (
        _alias_binding(1, IdentityAuthority.SEARCH_CONFIRMED, tmdb_id="207468"),
        _alias_binding(2, IdentityAuthority.FALLBACK, tmdb_id=None),
    )

    identities = identity_inputs.alias_identities(bindings)

    resolved = identities[("series", "kaijuu 8 gou")]
    assert resolved.tmdb_id == "207468"
    assert resolved.authority is IdentityAuthority.SEARCH_CONFIRMED


def test_equally_authoritative_alias_owners_remain_ambiguous() -> None:
    bindings = (
        _alias_binding(1, IdentityAuthority.SEARCH_CONFIRMED, tmdb_id="207468"),
        _alias_binding(2, IdentityAuthority.SEARCH_CONFIRMED, tmdb_id="999999"),
    )

    assert identity_inputs.alias_identities(bindings) == {}


@pytest.mark.asyncio
async def test_missing_metadata_enrichment_preserves_authoritative_identity() -> None:
    authoritative = MediaIdentity(
        tmdb_id="91768",
        title="Ascendance of a Bookworm",
        year=None,
        media_type="tv",
        authority=IdentityAuthority.MANUAL,
        library_category="anime",
    )
    by_torrent_id = {"44": authoritative}
    by_info_hash = {"abc123": authoritative}

    class ExactMetadataResolver:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        async def metadata_for_tmdb_id(self, external_id: str, media_type: str) -> MediaIdentity:
            self.calls.append((external_id, media_type))
            return MediaIdentity(
                tmdb_id=external_id,
                title="Provider title must not replace the canonical title",
                year=2019,
                media_type="tv",
                poster_path="/bookworm.jpg",
            )

    resolver = ExactMetadataResolver()
    await identity_inputs.enrich_missing_metadata(
        cast(MediaIdentityResolver, resolver),
        by_torrent_id,
        by_info_hash,
    )

    assert resolver.calls == [("91768", "tv")]
    for identity in (*by_torrent_id.values(), *by_info_hash.values()):
        assert identity.tmdb_id == "91768"
        assert identity.title == "Ascendance of a Bookworm"
        assert identity.year == 2019
        assert identity.poster_path == "/bookworm.jpg"
        assert identity.authority is IdentityAuthority.MANUAL
        assert identity.library_category == "anime"


def _alias_binding(
    media_item_id: int,
    authority: IdentityAuthority,
    *,
    tmdb_id: str | None,
) -> AliasIdentityBinding:
    return AliasIdentityBinding(
        normalized_alias="kaijuu 8 gou",
        identity=PersistedMediaIdentity(
            media_item_id=media_item_id,
            content_kind="series",
            title="Kaiju No. 8" if tmdb_id else "Kaijuu 8 gou",
            year=2024 if tmdb_id else None,
            tmdb_id=tmdb_id,
            provider_media_kind="tv" if tmdb_id else None,
            authority=authority.value,
            authoritative=authority.authoritative,
            confidence=100 if authority.authoritative else None,
            resolver_version="test",
            library_category="anime",
        ),
    )
