from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.media_identity import (
    AliasIdentityBinding,
    MediaIdentityRepository,
    PersistedMediaIdentity,
    SourceIdentityBinding,
)
from app.db.repositories.stream_selection import StreamSelectionRecord, StreamSelectionRepository
from app.domain.media_identity import (
    IdentityAuthority,
    identity_authority_priority,
    parse_library_category,
)
from app.sync.media_identity import MediaIdentity, MediaIdentityResolver


@dataclass(frozen=True, slots=True)
class IdentityInputs:
    by_torrent_id: dict[str, MediaIdentity]
    by_info_hash: dict[str, MediaIdentity]
    by_alias: dict[tuple[str, str], MediaIdentity]


async def selected_media_identities(
    repository: StreamSelectionRepository,
    selections: tuple[StreamSelectionRecord, ...],
    resolver: MediaIdentityResolver,
) -> tuple[dict[str, MediaIdentity], dict[str, MediaIdentity]]:
    by_torrent_id: dict[str, MediaIdentity] = {}
    by_info_hash: dict[str, MediaIdentity] = {}
    resolved_external_ids: dict[tuple[str, str], MediaIdentity | None] = {}
    for selection in selections:
        identity = await _selection_media_identity(
            repository,
            selection,
            resolver,
            resolved_external_ids,
        )
        if identity is None or identity.tmdb_id is None:
            continue
        if selection.torbox_torrent_id is not None:
            by_torrent_id[selection.torbox_torrent_id] = identity
        if selection.info_hash is not None:
            by_info_hash[selection.info_hash.casefold()] = identity
    return by_torrent_id, by_info_hash


async def identity_inputs(
    session: AsyncSession,
    selection_repository: StreamSelectionRepository,
    selected_streams: tuple[StreamSelectionRecord, ...],
    resolver: MediaIdentityResolver,
) -> IdentityInputs:
    by_torrent_id, by_info_hash = await selected_media_identities(
        selection_repository,
        selected_streams,
        resolver,
    )
    identity_repository = MediaIdentityRepository(session)
    merge_source_bindings(
        by_torrent_id,
        by_info_hash,
        await identity_repository.source_bindings(),
    )
    by_alias = alias_identities(await identity_repository.alias_bindings())
    await enrich_missing_metadata(
        resolver,
        by_torrent_id,
        by_info_hash,
        by_alias,
    )
    return IdentityInputs(
        by_torrent_id=by_torrent_id,
        by_info_hash=by_info_hash,
        by_alias=by_alias,
    )


async def enrich_missing_metadata(
    resolver: MediaIdentityResolver,
    *identity_maps: dict[Any, MediaIdentity],
) -> None:
    """Fill absent provider metadata without replacing established identity fields."""
    enriched: dict[tuple[str, str], MediaIdentity | None] = {}
    for identities in identity_maps:
        for key, identity in tuple(identities.items()):
            if identity.tmdb_id is None or (
                identity.year is not None and identity.poster_path is not None
            ):
                continue
            provider_key = (identity.tmdb_id, identity.media_type)
            if provider_key not in enriched:
                enriched[provider_key] = await resolver.metadata_for_tmdb_id(*provider_key)
            metadata = enriched[provider_key]
            if metadata is None:
                continue
            identities[key] = replace(
                identity,
                year=identity.year if identity.year is not None else metadata.year,
                poster_path=identity.poster_path or metadata.poster_path,
            )


async def _selection_media_identity(
    repository: StreamSelectionRepository,
    selection: StreamSelectionRecord,
    resolver: MediaIdentityResolver,
    resolved_external_ids: dict[tuple[str, str], MediaIdentity | None],
) -> MediaIdentity | None:
    stored = _stored_media_identity(selection)
    if stored is not None:
        return stored
    external_id = selection.media_id.split(":", maxsplit=1)[0]
    external_key = (external_id, selection.media_type)
    if external_key not in resolved_external_ids:
        resolved_external_ids[external_key] = await resolver.resolve_external_id(
            external_id,
            selection.media_type,
        )
    identity = resolved_external_ids[external_key]
    if identity is None or identity.tmdb_id is None:
        return identity
    confirmed = replace(identity, authority=IdentityAuthority.SEARCH_CONFIRMED)
    await repository.update_media_identity(
        selection.stream_key,
        tmdb_id=identity.tmdb_id,
        media_title=identity.title,
        media_year=identity.year,
        media_poster_path=identity.poster_path,
    )
    return confirmed


def _stored_media_identity(selection: StreamSelectionRecord) -> MediaIdentity | None:
    if selection.tmdb_id is None or selection.media_title is None:
        return None
    authority = IdentityAuthority(selection.identity_authority)
    return MediaIdentity(
        tmdb_id=selection.tmdb_id,
        title=selection.media_title,
        year=selection.media_year,
        media_type="movie" if selection.media_type == "movie" else "tv",
        poster_path=selection.media_poster_path,
        authority=authority,
        confidence=100 if authority.authoritative else None,
    )


def merge_source_bindings(
    by_torrent_id: dict[str, MediaIdentity],
    by_info_hash: dict[str, MediaIdentity],
    persisted: tuple[SourceIdentityBinding, ...],
) -> None:
    for record in persisted:
        candidates = [_media_identity(record.identity)]
        if record.source_kind == "torrents" and record.source_item_id is not None:
            selected = by_torrent_id.get(record.source_item_id)
            if selected is not None:
                candidates.append(selected)
        if record.info_hash is not None:
            selected = by_info_hash.get(record.info_hash.casefold())
            if selected is not None:
                candidates.append(selected)
        identity = max(
            candidates, key=lambda candidate: identity_authority_priority(candidate.authority)
        )
        if record.source_kind == "torrents" and record.source_item_id is not None:
            _merge_source_identity(by_torrent_id, record.source_item_id, identity)
        if record.info_hash is not None:
            _merge_source_identity(by_info_hash, record.info_hash.casefold(), identity)


def alias_identities(
    bindings: tuple[AliasIdentityBinding, ...],
) -> dict[tuple[str, str], MediaIdentity]:
    candidates: dict[tuple[str, str], list[tuple[int, MediaIdentity]]] = {}
    for binding in bindings:
        key = (binding.identity.content_kind, binding.normalized_alias)
        candidates.setdefault(key, []).append(
            (binding.identity.media_item_id, _media_identity(binding.identity))
        )

    identities: dict[tuple[str, str], MediaIdentity] = {}
    for key, key_candidates in candidates.items():
        highest_priority = max(
            identity_authority_priority(identity.authority) for _, identity in key_candidates
        )
        winners = [
            (owner, identity)
            for owner, identity in key_candidates
            if identity_authority_priority(identity.authority) == highest_priority
        ]
        if len({owner for owner, _ in winners}) == 1:
            identities[key] = winners[0][1]
    return identities


def _merge_source_identity(
    identities: dict[str, MediaIdentity],
    source_key: str,
    identity: MediaIdentity,
) -> None:
    current = identities.get(source_key)
    if current is None or identity_authority_priority(
        identity.authority
    ) >= identity_authority_priority(current.authority):
        identities[source_key] = identity


def _media_identity(identity: PersistedMediaIdentity) -> MediaIdentity:
    authority = IdentityAuthority(identity.authority)
    return MediaIdentity(
        tmdb_id=identity.tmdb_id,
        title=identity.title,
        year=identity.year,
        poster_path=identity.poster_path,
        media_type=(
            identity.provider_media_kind or ("movie" if identity.content_kind == "movie" else "tv")
        ),
        authority=authority,
        confidence=identity.confidence,
        resolver_version=identity.resolver_version or "persisted-v1",
        library_category=(
            parse_library_category(identity.library_category)
            if identity.library_category is not None
            else None
        ),
    )
