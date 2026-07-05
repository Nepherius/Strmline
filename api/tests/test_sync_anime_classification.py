from typing import override

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.providers.anilist.client import AniListClientError
from app.sync.anime_classification import SafeAniListAnimeClassifier


class FakeAnimeMetadataService:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error

    async def has_anime_match(self, title: str, *, year: int | None = None) -> bool:
        _ = title
        _ = year
        if self.error is not None:
            raise self.error
        return True


@pytest.mark.asyncio
async def test_safe_anilist_classifier_returns_false_on_provider_error() -> None:
    service = FakeAnimeMetadataService(error=AniListClientError("AniList request failed."))

    result = await SafeAniListAnimeClassifier(service).has_anime_match("Frieren", year=2023)

    assert result is False


@pytest.mark.asyncio
async def test_safe_anilist_classifier_returns_false_on_cache_error() -> None:
    service = FakeAnimeMetadataService(error=SQLAlchemyError("cache table unavailable"))

    result = await SafeAniListAnimeClassifier(service).has_anime_match("Frieren", year=2023)

    assert result is False


@pytest.mark.asyncio
async def test_safe_anilist_classifier_does_not_hide_unexpected_errors() -> None:
    class BrokenAnimeMetadataService(FakeAnimeMetadataService):
        @override
        async def has_anime_match(self, title: str, *, year: int | None = None) -> bool:
            _ = title
            _ = year
            raise ValueError("bad test service")

    with pytest.raises(ValueError, match="bad test service"):
        _ = await SafeAniListAnimeClassifier(BrokenAnimeMetadataService()).has_anime_match(
            "Frieren", year=2023
        )
