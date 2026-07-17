from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.library_exclusion import (
    BackingProviderItem,
    LibraryExclusionRepository,
)
from app.library.removal import StagedLibraryRemoval, stage_library_prefix_removal
from app.providers.torbox.client import TorBoxAPIError, TorBoxClient


class LibraryRemovalProviderError(RuntimeError):
    """Raised after a provider failure has been compensated locally."""


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
        await session.commit()
    except Exception:
        await session.rollback()
        staged.restore()
        raise

    removed_torbox_items = 0
    if torbox is not None:
        try:
            async with client_factory(
                api_key=torbox.api_key,
                base_url=torbox.base_url,
                timeout=torbox.timeout,
            ) as client:
                for item in backing_items:
                    await client.delete_download(item.kind, item.item_id)
                    removed_torbox_items += 1
        except TorBoxAPIError as error:
            await _compensate_local_removal(session, repository, relative_prefix, staged)
            raise LibraryRemovalProviderError("TorBox operation failed.") from error

    removal = staged.finalize()
    return LibraryRemovalOutcome(
        removed_files=removal.removed_files,
        removed_torbox_items=removed_torbox_items,
    )


async def _compensate_local_removal(
    session: AsyncSession,
    repository: LibraryExclusionRepository,
    relative_prefix: str,
    staged: StagedLibraryRemoval,
) -> None:
    await session.rollback()
    try:
        _ = await repository.remove(relative_prefix)
        await session.commit()
    finally:
        staged.restore()
