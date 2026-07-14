from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, cast
from urllib.parse import quote

from anyio.to_thread import run_sync
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import FileResponse

from app.api.provider_config import effective_tmdb_key, effective_torbox_key
from app.core.config import get_settings
from app.db.dependencies import get_db_session, get_optional_db_session
from app.db.repositories.classification_override import ClassificationOverrideRepository
from app.db.repositories.library_exclusion import LibraryExclusionRepository
from app.db.repositories.media_metadata import MediaMetadataRepository
from app.library.classification_override import (
    LibraryClassificationOverride,
    target_prefix_for_override,
)
from app.library.entries import LibraryCategory
from app.library.metadata_refresh import MetadataRefreshError, refresh_library_metadata
from app.library.posters import poster_for_tmdb_id
from app.library.removal import LibraryRemovalResult, remove_library_prefix
from app.library.summary import (
    LibraryDuplicateGroup,
    LibraryEntrySummary,
    LibraryFile,
    LibrarySummary,
    summarize_library,
)
from app.library.validation import (
    LibraryValidationIssue,
    LibraryValidationReport,
    validate_jellyfin_library,
)
from app.providers.tmdb.client import TmdbClient, TmdbClientError
from app.providers.tmdb.posters import TmdbPosterClient, TmdbPosterError
from app.providers.torbox.client import TorBoxAPIError, TorBoxClient

router = APIRouter(prefix="/api/library", tags=["library"])
logger = logging.getLogger(__name__)


class LibraryFileResponse(BaseModel):
    category: str
    title: str
    relative_path: str


class LibraryDuplicateGroupResponse(BaseModel):
    key: str
    files: list[LibraryFileResponse]


class LibraryEntryResponse(BaseModel):
    key: str
    category: str
    title: str
    relative_path: str
    file_count: int
    poster_url: str | None


class LibrarySummaryResponse(BaseModel):
    configured: bool
    root: str | None
    exists: bool
    total_files: int
    category_counts: dict[str, int]
    files: list[LibraryFileResponse]
    entries: list[LibraryEntryResponse]
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


class LibraryRemoveRequest(BaseModel):
    category: str = Field(pattern=r"^(movies|shows|anime)$")
    title: str = Field(min_length=1, max_length=300)
    relative_path: str = Field(min_length=1, max_length=1000)
    remove_torbox: bool = True


class LibraryRemoveResponse(BaseModel):
    ok: bool
    message: str
    removed_files: int
    removed_torbox_items: int


class LibraryMetadataRefreshRequest(BaseModel):
    category: str = Field(pattern=r"^(movies|shows|anime)$")
    relative_path: str = Field(min_length=1, max_length=1000)


class LibraryMetadataRefreshResponse(BaseModel):
    ok: bool
    message: str
    refreshed_posters: int


class ClassificationOverrideRequest(BaseModel):
    source_category: str = Field(pattern=r"^(movies|shows|anime)$")
    source_prefix: str = Field(min_length=1, max_length=1000)
    title: str = Field(min_length=1, max_length=300)
    target_category: str = Field(pattern=r"^(movies|shows|anime)$")


class ClassificationOverrideDeleteRequest(BaseModel):
    source_category: str = Field(pattern=r"^(movies|shows|anime)$")
    source_prefix: str = Field(min_length=1, max_length=1000)


class ClassificationOverrideResponse(BaseModel):
    source_category: str
    source_prefix: str
    title: str
    target_category: str
    target_prefix: str


async def get_library_root() -> Path:
    return get_settings().library_root


@router.get("/summary", response_model=LibrarySummaryResponse)
async def library_summary(
    session: Annotated[AsyncSession | None, Depends(get_optional_db_session)],
    library_root: Annotated[Path, Depends(get_library_root)],
) -> LibrarySummaryResponse:
    summary = await _summarize_library(library_root)
    poster_urls = await _entry_poster_urls(session, library_root, summary.entries)
    return LibrarySummaryResponse(
        configured=True,
        root=str(summary.root),
        exists=summary.exists,
        total_files=summary.total_files,
        category_counts=summary.category_counts,
        files=[_file_response(file) for file in summary.files],
        entries=[
            _entry_response(entry, poster_urls.get(entry.relative_path))
            for entry in summary.entries
        ],
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


@router.get("/poster")
async def library_poster(
    relative_path: Annotated[str, Query(min_length=1, max_length=1000)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    library_root: Annotated[Path, Depends(get_library_root)],
) -> FileResponse:
    record = await MediaMetadataRepository(session).find_for_library_prefix(relative_path)
    if record is None or record.media_item.tmdb_id is None:
        raise HTTPException(status_code=404, detail="Poster not found.")
    try:
        poster = poster_for_tmdb_id(library_root, record.media_item.tmdb_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if poster is None:
        raise HTTPException(status_code=404, detail="Poster not found.")
    return FileResponse(poster)


@router.get("/classification-overrides", response_model=list[ClassificationOverrideResponse])
async def classification_overrides(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[ClassificationOverrideResponse]:
    overrides = await ClassificationOverrideRepository(session).list_all()
    return [_classification_override_response(override) for override in overrides]


@router.post("/classification-overrides", response_model=ClassificationOverrideResponse)
async def save_classification_override(
    request: ClassificationOverrideRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ClassificationOverrideResponse:
    _validate_relative_prefix(request.source_prefix, request.source_category)
    if request.target_category == request.source_category:
        raise HTTPException(status_code=400, detail="Target category must be different.")
    override = await ClassificationOverrideRepository(session).upsert(
        source_category=_category(request.source_category),
        source_prefix=request.source_prefix,
        title=request.title,
        target_category=_category(request.target_category),
    )
    await session.commit()
    return _classification_override_response(override)


@router.delete("/classification-overrides", status_code=204)
async def delete_classification_override(
    request: ClassificationOverrideDeleteRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    _validate_relative_prefix(request.source_prefix, request.source_category)
    _ = await ClassificationOverrideRepository(session).delete(request.source_prefix)
    await session.commit()


@router.delete("/entries", response_model=LibraryRemoveResponse)
async def remove_library_entry(
    request: LibraryRemoveRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    library_root: Annotated[Path, Depends(get_library_root)],
) -> LibraryRemoveResponse:
    _validate_relative_prefix(request.relative_path, request.category)
    settings = get_settings()
    torbox_api_key = await effective_torbox_key(session, settings)
    if request.remove_torbox and torbox_api_key is None:
        raise HTTPException(status_code=400, detail="TorBox API key is not configured.")

    repository = LibraryExclusionRepository(session)
    removed_torbox_items = 0
    if request.remove_torbox:
        backing_items = await repository.backing_items(request.relative_path)
        try:
            async with TorBoxClient(
                api_key=torbox_api_key or "",
                base_url=settings.torbox_base_url,
                timeout=settings.outbound_timeout_seconds,
            ) as client:
                for item in backing_items:
                    await client.delete_download(item.kind, item.item_id)
                    removed_torbox_items += 1
        except TorBoxAPIError as error:
            await session.rollback()
            logger.warning("TorBox library removal failed.")
            raise HTTPException(status_code=503, detail="TorBox operation failed.") from error

    await repository.add(
        category=request.category,
        title=request.title,
        relative_prefix=request.relative_path,
    )
    removal = await _remove_library_prefix(library_root, request.relative_path)
    await session.commit()
    return LibraryRemoveResponse(
        ok=True,
        message="Library entry removed.",
        removed_files=removal.removed_files,
        removed_torbox_items=removed_torbox_items,
    )


@router.post("/entries/refresh-metadata", response_model=LibraryMetadataRefreshResponse)
async def refresh_entry_metadata(
    request: LibraryMetadataRefreshRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    library_root: Annotated[Path, Depends(get_library_root)],
) -> LibraryMetadataRefreshResponse:
    _validate_relative_prefix(request.relative_path, request.category)
    settings = get_settings()
    tmdb_api_key = await effective_tmdb_key(session, settings)
    if tmdb_api_key is None:
        raise HTTPException(status_code=400, detail="TMDB API key is not configured.")
    try:
        refreshed_posters = await refresh_library_metadata(
            session,
            library_root=library_root,
            relative_prefix=request.relative_path,
            tmdb_client=TmdbClient(
                api_key=tmdb_api_key,
                base_url=settings.tmdb_base_url,
                timeout_seconds=settings.outbound_timeout_seconds,
            ),
            poster_fetcher=TmdbPosterClient(timeout_seconds=settings.outbound_timeout_seconds),
        )
    except MetadataRefreshError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (TmdbClientError, TmdbPosterError) as error:
        raise HTTPException(status_code=503, detail="TMDB metadata refresh failed.") from error
    return LibraryMetadataRefreshResponse(
        ok=True,
        message="Metadata and poster refreshed.",
        refreshed_posters=refreshed_posters,
    )


def _duplicate_response(group: LibraryDuplicateGroup) -> LibraryDuplicateGroupResponse:
    return LibraryDuplicateGroupResponse(
        key=group.key,
        files=[_file_response(file) for file in group.files],
    )


def _entry_response(entry: LibraryEntrySummary, poster_url: str | None) -> LibraryEntryResponse:
    return LibraryEntryResponse(
        key=entry.key,
        category=entry.category,
        title=entry.title,
        relative_path=entry.relative_path,
        file_count=entry.file_count,
        poster_url=poster_url,
    )


def _classification_override_response(
    override: LibraryClassificationOverride,
) -> ClassificationOverrideResponse:
    return ClassificationOverrideResponse(
        source_category=override.source_category,
        source_prefix=override.source_prefix,
        title=override.title,
        target_category=override.target_category,
        target_prefix=target_prefix_for_override(override),
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


async def _entry_poster_urls(
    session: AsyncSession | None,
    library_root: Path,
    entries: tuple[LibraryEntrySummary, ...],
) -> dict[str, str]:
    if session is None:
        return {}
    tmdb_ids = await MediaMetadataRepository(session).tmdb_ids_for_library_prefixes(
        {entry.relative_path for entry in entries}
    )
    return {
        relative_prefix: f"/api/library/poster?relative_path={quote(relative_prefix, safe='')}"
        for relative_prefix, tmdb_id in tmdb_ids.items()
        if poster_for_tmdb_id(library_root, tmdb_id) is not None
    }


async def _validate_library(library_root: Path) -> LibraryValidationReport:
    return validate_jellyfin_library(library_root)


async def _remove_library_prefix(
    library_root: Path,
    relative_prefix: str,
) -> LibraryRemovalResult:
    return await run_sync(remove_library_prefix, library_root, relative_prefix)


def _validate_relative_prefix(relative_path: str, category: str) -> None:
    normalized = Path(relative_path)
    if normalized.is_absolute() or ".." in normalized.parts:
        raise HTTPException(status_code=400, detail="Library entry path is invalid.")
    if not relative_path.startswith(f"{category}/"):
        raise HTTPException(status_code=400, detail="Library entry category does not match path.")


def _category(value: str) -> LibraryCategory:
    if value in {"movies", "shows", "anime"}:
        return cast(LibraryCategory, value)
    raise HTTPException(status_code=400, detail="Library category is invalid.")
