from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MediaAlias, MediaExternalIdentity, MediaItem, SourceMediaBinding
from app.db.repositories.media_identity_records import (
    AliasIdentityBinding,
    PersistedMediaIdentity,
    SourceIdentityBinding,
)
from app.domain.media_identity import IdentityAuthority


class MediaIdentityQueryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def source_bindings(self) -> tuple[SourceIdentityBinding, ...]:
        result = await self._session.execute(
            select(SourceMediaBinding, MediaItem, MediaExternalIdentity)
            .join(MediaItem, MediaItem.id == SourceMediaBinding.media_item_id)
            .outerjoin(
                MediaExternalIdentity,
                (MediaExternalIdentity.media_item_id == MediaItem.id)
                & (MediaExternalIdentity.provider == "tmdb"),
            )
        )
        return tuple(
            SourceIdentityBinding(
                source_kind=binding.source_kind,
                source_item_id=binding.source_item_id,
                info_hash=binding.info_hash,
                identity=persisted_identity(media_item, external_identity, binding),
            )
            for binding, media_item, external_identity in result.all()
        )

    async def alias_bindings(self) -> tuple[AliasIdentityBinding, ...]:
        result = await self._session.execute(
            select(MediaAlias, MediaItem, MediaExternalIdentity)
            .join(MediaItem, MediaItem.id == MediaAlias.media_item_id)
            .outerjoin(
                MediaExternalIdentity,
                (MediaExternalIdentity.media_item_id == MediaItem.id)
                & (MediaExternalIdentity.provider == "tmdb"),
            )
        )
        return tuple(
            AliasIdentityBinding(
                normalized_alias=alias.normalized_alias,
                identity=persisted_identity(media_item, external_identity),
            )
            for alias, media_item, external_identity in result.all()
        )

    async def tmdb_identity_for_media(
        self,
        media_item_id: int,
    ) -> MediaExternalIdentity | None:
        result = await self._session.execute(
            select(MediaExternalIdentity)
            .where(
                MediaExternalIdentity.media_item_id == media_item_id,
                MediaExternalIdentity.provider == "tmdb",
            )
            .limit(1)
        )
        return result.scalar_one_or_none()


def persisted_identity(
    media_item: MediaItem,
    external_identity: MediaExternalIdentity | None,
    source_binding: SourceMediaBinding | None = None,
) -> PersistedMediaIdentity:
    authority = (
        source_binding.authority
        if source_binding is not None
        else external_identity.authority
        if external_identity is not None
        else IdentityAuthority.FALLBACK.value
    )
    return PersistedMediaIdentity(
        media_item_id=media_item.id,
        content_kind=media_item.content_kind,
        library_category=media_item.library_category,
        title=media_item.title,
        year=media_item.year,
        poster_path=media_item.poster_path,
        tmdb_id=external_identity.external_id if external_identity is not None else None,
        provider_media_kind=(
            external_identity.provider_media_kind if external_identity is not None else None
        ),
        authority=authority,
        authoritative=(
            source_binding.authoritative
            if source_binding is not None
            else external_identity.authoritative
            if external_identity is not None
            else False
        ),
        confidence=(
            source_binding.confidence
            if source_binding is not None
            else external_identity.confidence
            if external_identity is not None
            else None
        ),
        resolver_version=(
            source_binding.resolver_version
            if source_binding is not None
            else external_identity.resolver_version
            if external_identity is not None
            else None
        ),
    )
