from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.repositories.settings import AppSettingsRepository
from app.db.session import build_session_factory
from app.library.summary import (
    LibraryDuplicateGroup,
    LibraryFile,
    summarize_library,
)

router = APIRouter(prefix="/api/library", tags=["library"])


class LibraryFileResponse(BaseModel):
    category: str
    title: str
    relative_path: str


class LibraryDuplicateGroupResponse(BaseModel):
    key: str
    files: list[LibraryFileResponse]


class LibrarySummaryResponse(BaseModel):
    configured: bool
    root: str | None
    exists: bool
    total_files: int
    category_counts: dict[str, int]
    files: list[LibraryFileResponse]
    duplicate_groups: list[LibraryDuplicateGroupResponse]


async def get_library_root() -> Path | None:
    settings = get_settings()
    if settings.library_root is not None:
        return settings.library_root
    if settings.database_url is None:
        return None
    try:
        session_factory = build_session_factory(settings.database_url)
        async with session_factory() as session:
            snapshot = await AppSettingsRepository(session, settings).snapshot_with_env()
    except (OSError, SQLAlchemyError):
        return None
    if snapshot.library_root is None:
        return None
    return Path(snapshot.library_root)


@router.get("/summary", response_model=LibrarySummaryResponse)
async def library_summary(
    library_root: Annotated[Path | None, Depends(get_library_root)],
) -> LibrarySummaryResponse:
    if library_root is None:
        return _empty_response()
    summary = summarize_library(library_root)
    return LibrarySummaryResponse(
        configured=True,
        root=str(summary.root),
        exists=summary.exists,
        total_files=summary.total_files,
        category_counts=summary.category_counts,
        files=[_file_response(file) for file in summary.files],
        duplicate_groups=[_duplicate_response(group) for group in summary.duplicate_groups],
    )


def _empty_response() -> LibrarySummaryResponse:
    return LibrarySummaryResponse(
        configured=False,
        root=None,
        exists=False,
        total_files=0,
        category_counts={"movies": 0, "shows": 0, "anime": 0},
        files=[],
        duplicate_groups=[],
    )


def _duplicate_response(group: LibraryDuplicateGroup) -> LibraryDuplicateGroupResponse:
    return LibraryDuplicateGroupResponse(
        key=group.key,
        files=[_file_response(file) for file in group.files],
    )


def _file_response(file: LibraryFile) -> LibraryFileResponse:
    return LibraryFileResponse(
        category=file.category,
        title=file.title,
        relative_path=file.relative_path,
    )
