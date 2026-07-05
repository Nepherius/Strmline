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
from app.library.validation import (
    LibraryValidationIssue,
    LibraryValidationReport,
    validate_jellyfin_library,
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


class LibraryValidationIssueResponse(BaseModel):
    code: str
    message: str
    relative_path: str | None


class LibraryValidationResponse(BaseModel):
    configured: bool
    root: str | None
    exists: bool
    ok: bool
    total_files: int
    category_counts: dict[str, int]
    warnings: list[LibraryValidationIssueResponse]
    errors: list[LibraryValidationIssueResponse]


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


@router.get("/validation", response_model=LibraryValidationResponse)
async def library_validation(
    library_root: Annotated[Path, Depends(get_library_root)],
) -> LibraryValidationResponse:
    report = await _validate_library(library_root)
    return LibraryValidationResponse(
        configured=True,
        root=str(report.summary.root),
        exists=report.summary.exists,
        ok=report.ok,
        total_files=report.summary.total_files,
        category_counts=report.summary.category_counts,
        warnings=[_issue_response(issue) for issue in report.warnings],
        errors=[_issue_response(issue) for issue in report.errors],
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


def _issue_response(issue: LibraryValidationIssue) -> LibraryValidationIssueResponse:
    return LibraryValidationIssueResponse(
        code=issue.code,
        message=issue.message,
        relative_path=issue.relative_path,
    )


async def _summarize_library(library_root: Path) -> LibrarySummary:
    return await run_sync(summarize_library, library_root)


async def _validate_library(library_root: Path) -> LibraryValidationReport:
    return validate_jellyfin_library(library_root)
