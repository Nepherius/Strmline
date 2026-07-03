from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings
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


@router.get("/summary", response_model=LibrarySummaryResponse)
async def library_summary() -> LibrarySummaryResponse:
    settings = get_settings()
    if settings.library_root is None:
        return _empty_response()
    summary = summarize_library(settings.library_root)
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
