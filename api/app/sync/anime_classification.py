from __future__ import annotations

from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.repositories.anilist_cache import AniListCacheRepository
from app.providers.anilist.anime import AniListAnimeService
from app.providers.anilist.client import AniListClient, AniListClientError


class AnimeMetadataService(Protocol):
    async def has_anime_match(self, title: str, *, year: int | None = None) -> bool:
        """Return true when provider metadata confirms an anime title."""
        ...


class SafeAniListAnimeClassifier:
    def __init__(self, service: AnimeMetadataService) -> None:
        self._service = service

    async def has_anime_match(self, title: str, *, year: int | None = None) -> bool:
        try:
            return await self._service.has_anime_match(title, year=year)
        except (AniListClientError, SQLAlchemyError):
            return False


def build_anilist_anime_classifier(
    session: AsyncSession,
    settings: Settings,
) -> SafeAniListAnimeClassifier:
    return SafeAniListAnimeClassifier(
        AniListAnimeService(
            cache_repository=AniListCacheRepository(session),
            anilist_client=AniListClient(
                base_url=settings.anilist_base_url,
                timeout_seconds=settings.outbound_timeout_seconds,
            ),
        )
    )
