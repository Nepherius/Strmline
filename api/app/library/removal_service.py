from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.library_exclusion import (
    BackingProviderItem,
    LibraryExclusionRepository,
)
from app.db.repositories.stream_selection import StreamSelectionRepository
from app.library.removal import stage_library_prefix_removal
from app.providers.torbox.client import TorBoxClient
from app.providers.torbox.removal import remove_torbox_items


class TorBoxRemovalClientFactory(Protocol):
    def __call__(self, *, api_key: str, base_url: str, timeout: float) -> TorBoxClient: ...


@dataclass(frozen=True, slots=True)
class TorBoxRemovalConfig:
    api_key: str
    base_url: str
    timeout: float


@dataclass(frozen=True, slots=True)
class LibraryRemovalOutcome:
    removed_files: int
    removed_torbox_items: int
    torbox_removal_failed: bool = False


async def remove_library_media(  # noqa: PLR0913
    session: AsyncSession,
    *,
    library_root: Path,
    category: str,
    title: str,
    relative_prefix: str,
    backing_items: tuple[BackingProviderItem, ...],
    torbox: TorBoxRemovalConfig | None,
    client_factory: TorBoxRemovalClientFactory = TorBoxClient,
) -> LibraryRemovalOutcome:
    repository = LibraryExclusionRepository(session)
    await session.commit()
    staged = stage_library_prefix_removal(library_root, relative_prefix)
    try:
        await repository.add(
            category=category,
            title=title,
            relative_prefix=relative_prefix,
        )
        _ = await repository.remove_generated_files(relative_prefix)
        _ = await StreamSelectionRepository(session).delete_for_torbox_items(
            {item.item_id for item in backing_items if item.kind == "torrents"}
        )
        await session.commit()
    except Exception:
        await session.rollback()
        staged.restore()
        raise

    removed_torbox_items = 0
    torbox_removal_failed = False
    if torbox is not None:
        async with client_factory(
            api_key=torbox.api_key,
            base_url=torbox.base_url,
            timeout=torbox.timeout,
        ) as client:
            provider_removal = await remove_torbox_items(client, backing_items)
        removed_torbox_items = provider_removal.removed
        torbox_removal_failed = not provider_removal.complete

    removal = staged.finalize()
    return LibraryRemovalOutcome(
        removed_files=removal.removed_files,
        removed_torbox_items=removed_torbox_items,
        torbox_removal_failed=torbox_removal_failed,
    )
