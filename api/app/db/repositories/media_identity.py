from __future__ import annotations

from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    LibraryEntry,
    MediaAlias,
    MediaExternalIdentity,
    MediaItem,
    SourceMediaBinding,
)
from app.db.repositories.media_identity_queries import persisted_identity
from app.db.repositories.media_identity_records import (
    AliasIdentityBinding,
    MediaIdentityWrite,
    PersistedMediaIdentity,
    SourceBindingWrite,
    SourceIdentityBinding,
)
from app.domain.media_identity import (
    ContentKind,
    IdentityAuthority,
    LibraryCategory,
    ProviderMediaKind,
    identity_authority_priority,
    provider_kind_for_content,
)
from app.domain.normalization import normalize_info_hash, normalize_title_for_identity


class AuthoritativeIdentityConflictError(RuntimeError):
    """Raised when an operation would replace a different authoritative identity."""


__all__ = [
    "AliasIdentityBinding",
    "AuthoritativeIdentityConflictError",
    "MediaIdentityRepository",
    "MediaIdentityWrite",
    "PersistedMediaIdentity",
    "SourceBindingWrite",
    "SourceIdentityBinding",
]

_persisted_identity = persisted_identity


class MediaIdentityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure_media(
        self,
        write: MediaIdentityWrite,
    ) -> MediaItem:
        await self._conflict_lock(
            "external" if write.tmdb_id is not None else "fallback",
            (
                f"tmdb:{write.provider_media_kind.value}:{write.tmdb_id}"
                if write.tmdb_id is not None
                else ":".join(
                    (
                        write.content_kind.value,
                        normalize_title_for_identity(write.title),
                        str(write.year),
                    )
                )
            ),
        )
        external_identity = None
        if write.tmdb_id is not None:
            external_identity = await self._external_identity(
                "tmdb", write.provider_media_kind, write.tmdb_id
            )
        if external_identity is not None:
            media_item = external_identity.media_item
            self._apply_stronger_identity(
                media_item,
                external_identity,
                write,
            )
            await self._alias(media_item, write.title, source=write.authority.value)
            return media_item

        media_item = await self._unidentified_media(
            write.content_kind,
            write.library_category,
            write.title,
            write.year,
        )
        if media_item is None:
            media_item = MediaItem(
                content_kind=write.content_kind.value,
                library_category=write.library_category,
                title=write.title,
                year=write.year,
                poster_path=write.poster_path,
            )
            self._session.add(media_item)
            await self._session.flush()

        if write.tmdb_id is not None:
            external_identity = MediaExternalIdentity(
                media_item_id=media_item.id,
                provider="tmdb",
                provider_media_kind=write.provider_media_kind.value,
                external_id=write.tmdb_id,
                authority=write.authority.value,
                authoritative=write.authority.authoritative,
                confidence=write.confidence,
                resolver_version=write.resolver_version,
            )
            self._session.add(external_identity)
        await self._alias(media_item, write.title, source=write.authority.value)
        await self._session.flush()
        return media_item

    async def bind_sources(
        self,
        media_item: MediaItem,
        write: SourceBindingWrite,
    ) -> None:
        normalized_hash = normalize_info_hash(write.info_hash)
        if write.source_item_id is not None:
            await self._bind_source_key(
                media_item,
                SourceBindingWrite(
                    source_kind=write.source_kind,
                    source_item_id=write.source_item_id,
                    info_hash=None,
                    source_title=write.source_title,
                    authority=write.authority,
                    confidence=write.confidence,
                    resolver_version=write.resolver_version,
                ),
            )
        if normalized_hash is not None:
            await self._bind_source_key(
                media_item,
                SourceBindingWrite(
                    source_kind=write.source_kind,
                    source_item_id=None,
                    info_hash=normalized_hash,
                    source_title=write.source_title,
                    authority=write.authority,
                    confidence=write.confidence,
                    resolver_version=write.resolver_version,
                ),
            )
        await self._alias(media_item, write.source_title, source=write.authority.value)
        await self._session.flush()

    async def set_manual_tmdb_identity(
        self,
        media_item: MediaItem,
        tmdb_id: str,
    ) -> MediaItem:
        provider_kind = provider_kind_for_content(media_item.content_kind)
        await self._conflict_lock("external", f"tmdb:{provider_kind.value}:{tmdb_id}")
        owner_identity = await self._external_identity("tmdb", provider_kind, tmdb_id)
        if owner_identity is not None and owner_identity.media_item_id != media_item.id:
            media_item = await self._merge_media_items(owner_identity.media_item, media_item)

        current = await self._identity_for_media(media_item.id, "tmdb")
        if current is None:
            self._session.add(
                MediaExternalIdentity(
                    media_item_id=media_item.id,
                    provider="tmdb",
                    provider_media_kind=provider_kind.value,
                    external_id=tmdb_id,
                    authority=IdentityAuthority.MANUAL.value,
                    authoritative=True,
                    confidence=100,
                    resolver_version=None,
                )
            )
        else:
            if current.external_id != tmdb_id:
                media_item.poster_path = None
            current.provider_media_kind = provider_kind.value
            current.external_id = tmdb_id
            current.authority = IdentityAuthority.MANUAL.value
            current.authoritative = True
            current.confidence = 100
            current.resolver_version = None
        _ = await self._session.execute(
            update(SourceMediaBinding)
            .where(SourceMediaBinding.media_item_id == media_item.id)
            .values(
                authority=IdentityAuthority.MANUAL.value,
                authoritative=True,
                confidence=100,
                resolver_version=None,
            )
        )
        await self._session.flush()
        return media_item

    async def delete_orphaned_media(self) -> int:
        result = await self._session.execute(
            delete(MediaItem)
            .where(~MediaItem.library_entries.any(), ~MediaItem.source_bindings.any())
            .returning(MediaItem.id)
        )
        return len(tuple(result.scalars()))

    async def _bind_source_key(
        self,
        media_item: MediaItem,
        write: SourceBindingWrite,
    ) -> None:
        await self._conflict_lock(
            "source",
            (
                f"{write.source_kind}:item:{write.source_item_id}"
                if write.source_item_id is not None
                else f"hash:{write.info_hash}"
            ),
        )
        statement = select(SourceMediaBinding)
        if write.source_item_id is not None:
            statement = statement.where(
                SourceMediaBinding.source_kind == write.source_kind,
                SourceMediaBinding.source_item_id == write.source_item_id,
            )
        else:
            statement = statement.where(SourceMediaBinding.info_hash == write.info_hash)
        result = await self._session.execute(statement)
        binding = result.scalar_one_or_none()
        if binding is None:
            self._session.add(
                SourceMediaBinding(
                    media_item_id=media_item.id,
                    source_kind=write.source_kind,
                    source_item_id=write.source_item_id,
                    info_hash=write.info_hash,
                    authority=write.authority.value,
                    authoritative=write.authority.authoritative,
                    confidence=write.confidence,
                    resolver_version=write.resolver_version,
                )
            )
            return
        if binding.media_item_id != media_item.id:
            if binding.authoritative and not write.authority.authoritative:
                return
            if binding.authoritative and write.authority.authoritative:
                raise AuthoritativeIdentityConflictError(
                    "Source is already bound to a different authoritative media identity."
                )
            binding.media_item_id = media_item.id
        if write.authority.authoritative or not binding.authoritative:
            binding.authority = write.authority.value
            binding.authoritative = write.authority.authoritative
            binding.confidence = write.confidence
            binding.resolver_version = write.resolver_version

    async def _external_identity(
        self,
        provider: str,
        provider_kind: ProviderMediaKind,
        external_id: str,
    ) -> MediaExternalIdentity | None:
        result = await self._session.execute(
            select(MediaExternalIdentity)
            .options(selectinload(MediaExternalIdentity.media_item))
            .where(
                MediaExternalIdentity.provider == provider,
                MediaExternalIdentity.provider_media_kind == provider_kind.value,
                MediaExternalIdentity.external_id == external_id,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _identity_for_media(
        self,
        media_item_id: int,
        provider: str,
    ) -> MediaExternalIdentity | None:
        result = await self._session.execute(
            select(MediaExternalIdentity)
            .where(
                MediaExternalIdentity.media_item_id == media_item_id,
                MediaExternalIdentity.provider == provider,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _unidentified_media(
        self,
        content_kind: ContentKind,
        library_category: LibraryCategory,
        title: str,
        year: int | None,
    ) -> MediaItem | None:
        result = await self._session.execute(
            select(MediaItem)
            .where(
                MediaItem.content_kind == content_kind.value,
                MediaItem.library_category == library_category,
                MediaItem.title == title,
                (MediaItem.year == year) if year is not None else MediaItem.year.is_(None),
                ~MediaItem.external_identities.any(),
            )
            .order_by(MediaItem.id)
            .limit(2)
        )
        matches = tuple(result.scalars())
        return matches[0] if len(matches) == 1 else None

    async def _alias(self, media_item: MediaItem, alias: str, *, source: str) -> None:
        normalized = normalize_title_for_identity(alias)
        if not normalized:
            return
        result = await self._session.execute(
            select(MediaAlias).where(
                MediaAlias.media_item_id == media_item.id,
                MediaAlias.normalized_alias == normalized,
            )
        )
        if result.scalar_one_or_none() is None:
            self._session.add(
                MediaAlias(
                    media_item_id=media_item.id,
                    content_kind=media_item.content_kind,
                    alias=alias,
                    normalized_alias=normalized,
                    source=source,
                )
            )

    async def _merge_media_items(self, target: MediaItem, duplicate: MediaItem) -> MediaItem:
        _ = await self._session.execute(
            update(LibraryEntry)
            .where(LibraryEntry.media_item_id == duplicate.id)
            .values(media_item_id=target.id)
        )
        duplicate_bindings = await self._session.execute(
            select(SourceMediaBinding).where(SourceMediaBinding.media_item_id == duplicate.id)
        )
        for binding in duplicate_bindings.scalars():
            existing = await self._matching_source_binding(target.id, binding)
            if existing is None:
                binding.media_item_id = target.id
                binding.authority = IdentityAuthority.MANUAL.value
                binding.authoritative = True
                binding.confidence = 100
                binding.resolver_version = None
                continue
            existing.authority = IdentityAuthority.MANUAL.value
            existing.authoritative = True
            existing.confidence = 100
            existing.resolver_version = None
            await self._session.delete(binding)
        duplicate_aliases = await self._session.execute(
            select(MediaAlias).where(MediaAlias.media_item_id == duplicate.id)
        )
        for alias in duplicate_aliases.scalars():
            await self._alias(target, alias.alias, source=alias.source)
        await self._session.delete(duplicate)
        return target

    async def _matching_source_binding(
        self,
        media_item_id: int,
        candidate: SourceMediaBinding,
    ) -> SourceMediaBinding | None:
        conditions = [SourceMediaBinding.media_item_id == media_item_id]
        if candidate.source_item_id is not None:
            conditions.extend(
                (
                    SourceMediaBinding.source_kind == candidate.source_kind,
                    SourceMediaBinding.source_item_id == candidate.source_item_id,
                )
            )
        else:
            conditions.append(SourceMediaBinding.info_hash == candidate.info_hash)
        result = await self._session.execute(select(SourceMediaBinding).where(*conditions))
        return result.scalar_one_or_none()

    async def _conflict_lock(self, namespace: str, value: str) -> None:
        bind = getattr(self._session, "bind", None)
        if bind is None or bind.dialect.name != "postgresql":
            return
        _ = await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"strmline:{namespace}:{value}"},
        )

    @staticmethod
    def _apply_stronger_identity(
        media_item: MediaItem,
        external_identity: MediaExternalIdentity,
        write: MediaIdentityWrite,
    ) -> None:
        current_authority = IdentityAuthority(external_identity.authority)
        if external_identity.authoritative:
            _fill_missing_metadata(media_item, write)
            return
        if write.authority.authoritative:
            media_item.title = write.title
            media_item.year = write.year
            media_item.poster_path = write.poster_path or media_item.poster_path
            external_identity.authority = write.authority.value
            external_identity.authoritative = True
            external_identity.confidence = write.confidence
            external_identity.resolver_version = write.resolver_version
            return
        _fill_missing_metadata(media_item, write)
        if identity_authority_priority(write.authority) > identity_authority_priority(
            current_authority
        ):
            external_identity.authority = write.authority.value
            external_identity.confidence = write.confidence
            external_identity.resolver_version = write.resolver_version


def _fill_missing_metadata(media_item: MediaItem, write: MediaIdentityWrite) -> None:
    if not media_item.title.strip():
        media_item.title = write.title
    if media_item.year is None:
        media_item.year = write.year
    if media_item.poster_path is None:
        media_item.poster_path = write.poster_path
