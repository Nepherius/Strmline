from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.providers.torbox.client import TorBoxAPIError
from app.providers.torbox.files import DownloadKind

logger = logging.getLogger(__name__)


class TorBoxRemovalTarget(Protocol):
    @property
    def kind(self) -> DownloadKind: ...

    @property
    def item_id(self) -> str: ...


class TorBoxRemovalClient(Protocol):
    async def delete_download(self, kind: DownloadKind, item_id: str) -> None: ...


@dataclass(frozen=True, slots=True)
class TorBoxItemRemoval:
    kind: DownloadKind
    item_id: str


@dataclass(frozen=True, slots=True)
class TorBoxRemovalResult:
    removed: int
    already_absent: int
    unconfirmed: int

    @property
    def complete(self) -> bool:
        return self.unconfirmed == 0


async def remove_torbox_items(
    client: TorBoxRemovalClient,
    targets: Iterable[TorBoxRemovalTarget],
) -> TorBoxRemovalResult:
    pending = tuple(targets)
    removed = 0
    already_absent = 0
    unconfirmed = 0
    for index, target in enumerate(pending):
        try:
            await client.delete_download(target.kind, target.item_id)
        except TorBoxAPIError as error:
            if error.error_code == "ITEM_NOT_FOUND":
                already_absent += 1
                continue
            unconfirmed += 1
            logger.warning(
                "TorBox item deletion was not confirmed kind=%s item_id=%s.",
                target.kind,
                target.item_id,
                exc_info=True,
            )
        except (httpx.HTTPError, OSError):
            unconfirmed += len(pending) - index
            logger.warning("TorBox was unavailable during item deletion.", exc_info=True)
            break
        else:
            removed += 1
    return TorBoxRemovalResult(
        removed=removed,
        already_absent=already_absent,
        unconfirmed=unconfirmed,
    )
