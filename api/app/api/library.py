from __future__ import annotations

from pathlib import Path
from typing import Annotated

from anyio.to_thread import run_sync
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import get_settings
from app.library.summary import (
    LibraryDuplicateGroup,
    LibraryFile,
    LibrarySummary,
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


async def get_library_root() -> Path:
    return get_settings().library_root


@router.get("/summary", response_model=LibrarySummaryResponse)
async def library_summary(
    library_root: Annotated[Path, Depends(get_library_root)],
) -> LibrarySummaryResponse:
    summary = await _summarize_library(library_root)
    return LibrarySummaryResponse(
        configured=True,
        root=str(summary.root),
        exists=summary.exists,
        total_files=summary.total_files,
        category_counts=summary.category_counts,
        files=[_file_response(file) for file in summary.files],
        duplicate_groups=[_duplicate_response(group) for group in summary.duplicate_groups],
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


async def _summarize_library(library_root: Path) -> LibrarySummary:
    return await run_sync(summarize_library, library_root)
