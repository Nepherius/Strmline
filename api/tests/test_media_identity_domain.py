from collections.abc import Callable

import pytest

from app.domain.media_identity import (
    ContentKind,
    ExternalMediaIdentity,
    IdentityAuthority,
    ProviderMediaKind,
    content_kind_for_category,
    content_kind_for_provider,
    parse_library_category,
    provider_kind_for_content,
    provider_kind_for_search,
    search_media_type_for_category,
)
from app.domain.normalization import (
    normalize_info_hash,
    normalize_source_path,
    normalize_title_for_identity,
)


@pytest.mark.parametrize("category", ["movies", "shows", "anime"])
def test_library_category_validation(category: str) -> None:
    assert parse_library_category(category) == category


def test_invalid_library_category_is_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid library category"):
        _ = parse_library_category("documentary")


@pytest.mark.parametrize(
    ("operation", "value"),
    [
        (content_kind_for_category, "documentary"),
        (provider_kind_for_content, "episode"),
        (provider_kind_for_search, "tv"),
        (content_kind_for_provider, "series"),
        (search_media_type_for_category, "documentary"),
    ],
)
def test_invalid_media_kind_values_are_rejected(
    operation: Callable[[str], object],
    value: str,
) -> None:
    with pytest.raises(ValueError, match=r"Invalid|not a valid"):
        _ = operation(value)


def test_media_kind_conversions_share_one_policy() -> None:
    assert content_kind_for_category("movies") is ContentKind.MOVIE
    assert content_kind_for_category("anime") is ContentKind.SERIES
    assert provider_kind_for_content(ContentKind.MOVIE) is ProviderMediaKind.MOVIE
    assert provider_kind_for_content(ContentKind.SERIES) is ProviderMediaKind.TV
    assert provider_kind_for_search("movie") is ProviderMediaKind.MOVIE
    assert provider_kind_for_search("series") is ProviderMediaKind.TV
    assert content_kind_for_provider(ProviderMediaKind.MOVIE) is ContentKind.MOVIE
    assert content_kind_for_provider(ProviderMediaKind.TV) is ContentKind.SERIES
    assert search_media_type_for_category("movies") == "movie"
    assert search_media_type_for_category("anime") == "series"


def test_external_identity_requires_provider_and_id() -> None:
    identity = ExternalMediaIdentity("tmdb", ProviderMediaKind.TV, "91768")
    assert identity.external_id == "91768"
    with pytest.raises(ValueError, match="provider"):
        _ = ExternalMediaIdentity(" ", ProviderMediaKind.TV, "91768")
    with pytest.raises(ValueError, match="External identity"):
        _ = ExternalMediaIdentity("tmdb", ProviderMediaKind.TV, " ")


def test_authoritative_identity_sources_are_explicit() -> None:
    assert IdentityAuthority.MANUAL.authoritative is True
    assert IdentityAuthority.SEARCH_CONFIRMED.authoritative is True
    assert IdentityAuthority.MIGRATED.authoritative is False
    assert IdentityAuthority.PROVIDER_RESOLVED.authoritative is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("A" * 40, "a" * 40),
        (f"  {'aB' * 20}  ", "ab" * 20),
        (None, None),
        ("  ", None),
    ],
)
def test_info_hash_normalization_is_idempotent(raw: str | None, expected: str | None) -> None:
    normalized = normalize_info_hash(raw)
    assert normalized == expected
    assert normalize_info_hash(normalized) == expected


def test_source_path_and_title_normalization_are_semantic_and_idempotent() -> None:
    assert normalize_source_path(r"Folder\\Season 01//Episode.mkv") == (
        "folder/season 01/episode.mkv"
    )
    title = normalize_title_for_identity("  Kaijuu  8-gou!! ")
    assert title == "kaijuu 8 gou"
    assert normalize_title_for_identity(title) == title
