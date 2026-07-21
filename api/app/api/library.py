from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

import httpx
from anyio.to_thread import run_sync
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import FileResponse

from app.api.library_classification import (
    delete_media_classification,
    save_media_classification,
)
from app.api.library_identity import require_matching_media_record, require_media_location
from app.api.provider_config import effective_tmdb_key, effective_torbox_key
from app.core.config import get_settings
from app.db.dependencies import get_db_session, get_optional_db_session
from app.db.repositories.classification_override import ClassificationOverrideRepository
from app.db.repositories.library_exclusion import LibraryExclusionRepository
from app.db.repositories.library_health import (
    LibraryHealthAggregate,
    LibraryHealthRepository,
    LibraryHealthStatus,
)
from app.db.repositories.media_identity import AuthoritativeIdentityConflictError
from app.db.repositories.media_metadata import (
    LibraryMediaRecord,
    LibraryPageEntry,
    LibraryPageOptions,
    MediaMetadataRepository,
)
from app.library.classification_override import (
    LibraryClassificationOverride,
    target_prefix_for_override,
)
from app.library.health import LibraryHealthCheckResult, check_library_health
from app.library.metadata_refresh import MetadataRefreshError
from app.library.metadata_update import refresh_tmdb_metadata
from app.library.posters import poster_for_tmdb_id
from app.library.removal_service import TorBoxRemovalConfig, remove_library_media
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
from app.providers.tmdb.client import TmdbClientError
from app.providers.tmdb.posters import TmdbPosterError
from app.providers.torbox.client import TorBoxAPIError, TorBoxClient
from app.sync.auto import auto_sync_after_action

router = APIRouter(prefix="/api/library", tags=["library"])
logger = logging.getLogger(__name__)
_health_check_lock = asyncio.Lock()


class LibraryFileResponse(BaseModel):
    category: str
    title: str
    relative_path: str


class LibraryDuplicateGroupResponse(BaseModel):
    key: str
    files: list[LibraryFileResponse]


class LibraryHealthSummaryResponse(BaseModel):
    status: LibraryHealthStatus
    total: int
    ready: int
    recoverable: int
    unavailable: int
    unknown: int
    checked_at: datetime | None


class LibraryEntryResponse(BaseModel):
    key: str
    category: str
    title: str
    relative_path: str
    file_count: int
    poster_url: str | None
    tmdb_id: int | None
    media_item_id: int | None
    health: LibraryHealthSummaryResponse


class LibraryHealthCheckResponse(BaseModel):
    checked_at: datetime
    checked_entries: int
    distinct_hashes: int
    ready: int
    recoverable: int
    unavailable: int
    unknown: int


class LibrarySummaryResponse(BaseModel):
    configured: bool
    root: str | None
    exists: bool
    total_files: int
    category_counts: dict[str, int]
    files: list[LibraryFileResponse]
    entries: list[LibraryEntryResponse]
    duplicate_groups: list[LibraryDuplicateGroupResponse]


class LibraryEntryPageResponse(BaseModel):
    entries: list[LibraryEntryResponse]
    limit: int
    total: int | None
    has_more: bool
    next_cursor: str | None
    total_files: int | None
    category_counts: dict[str, int] | None


class LibraryEntryPageRequest(BaseModel):
    limit: int = Field(default=50, ge=1, le=100)
    category: Literal["movies", "shows", "anime"] | None = None
    query: str = Field(default="", max_length=300)
    sort_key: Literal["title", "category", "relative_path"] = "title"
    direction: Literal["asc", "desc"] = "asc"
    include_overview: bool = True
    cursor: str | None = Field(default=None, max_length=1000)


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


class LibraryDiagnosticsResponse(LibraryValidationResponse):
    duplicate_groups: list[LibraryDuplicateGroupResponse]
    duplicate_file_count: int


class LibraryRemoveRequest(BaseModel):
    category: str = Field(pattern=r"^(movies|shows|anime)$")
    title: str = Field(min_length=1, max_length=300)
    relative_path: str = Field(min_length=1, max_length=1000)
    media_item_id: int | None = Field(default=None, ge=1)
    remove_torbox: bool = True


class LibraryRemoveResponse(BaseModel):
    ok: bool
    message: str
    removed_files: int
    removed_torbox_items: int
    torbox_removal_failed: bool = False
    auto_sync_status: str
    auto_sync_run_id: int | None


class LibraryMetadataRefreshRequest(BaseModel):
    category: str = Field(pattern=r"^(movies|shows|anime)$")
    relative_path: str = Field(min_length=1, max_length=1000)
    media_item_id: int = Field(ge=1)


class LibraryMetadataRefreshResponse(BaseModel):
    ok: bool
    message: str
    refreshed_posters: int


class LibraryTmdbIdUpdateRequest(BaseModel):
    category: str = Field(pattern=r"^(movies|shows|anime)$")
    relative_path: str = Field(min_length=1, max_length=1000)
    tmdb_id: int = Field(ge=1)
    media_item_id: int = Field(ge=1)


class LibraryTmdbIdUpdateResponse(BaseModel):
    ok: bool
    message: str
    tmdb_id: int
    refreshed_posters: int


class ClassificationOverrideRequest(BaseModel):
    media_item_id: int = Field(ge=1)
    target_category: str = Field(pattern=r"^(movies|shows|anime)$")


class ClassificationOverrideDeleteRequest(BaseModel):
    media_item_id: int = Field(ge=1)


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
    records = await _entry_records(session, summary.entries)
    return LibrarySummaryResponse(
        configured=True,
        root=str(summary.root),
        exists=summary.exists,
        total_files=summary.total_files,
        category_counts=summary.category_counts,
        files=[_file_response(file) for file in summary.files],
        entries=[
            _entry_response(entry, records.get(entry.relative_path), library_root)
            for entry in summary.entries
        ],
        duplicate_groups=[_duplicate_response(group) for group in summary.duplicate_groups],
    )


@router.get("/entries", response_model=LibraryEntryPageResponse)
async def library_entries(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    library_root: Annotated[Path, Depends(get_library_root)],
    request: Annotated[LibraryEntryPageRequest, Depends()],
) -> LibraryEntryPageResponse:
    try:
        page = await MediaMetadataRepository(session).library_page(
            LibraryPageOptions(
                limit=request.limit,
                category=request.category,
                query=request.query,
                sort_key=request.sort_key,
                direction=request.direction,
                include_overview=request.include_overview,
                cursor=request.cursor,
            )
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    health = await LibraryHealthRepository(session).aggregates_for_media(
        {(entry.media_item_id, entry.category) for entry in page.entries}
    )
    entries = [
        _page_entry_response(
            entry,
            library_root,
            health.get((entry.media_item_id, entry.category)),
        )
        for entry in page.entries
    ]
    return LibraryEntryPageResponse(
        entries=entries,
        limit=request.limit,
        total=page.total_matches,
        has_more=page.next_cursor is not None,
        next_cursor=page.next_cursor,
        total_files=page.total_files,
        category_counts=page.category_counts,
    )


@router.post("/health/check", response_model=LibraryHealthCheckResponse)
async def run_library_health_check(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> LibraryHealthCheckResponse:
    if _health_check_lock.locked():
        raise HTTPException(status_code=409, detail="A library health check is already running.")
    settings = get_settings()
    api_key = await effective_torbox_key(session, settings)
    if api_key is None:
        raise HTTPException(status_code=400, detail="TorBox API key is not configured.")
    try:
        async with _health_check_lock:
            async with TorBoxClient(
                api_key=api_key,
                base_url=settings.torbox_base_url,
                timeout=settings.outbound_timeout_seconds,
            ) as torbox_client:
                result = await check_library_health(
                    LibraryHealthRepository(session),
                    torbox_client,
                )
            await session.commit()
    except (OSError, ValueError, httpx.HTTPError, TorBoxAPIError) as error:
        await session.rollback()
        logger.warning("TorBox library health check failed: %s", error.__class__.__name__)
        raise HTTPException(
            status_code=503,
            detail="TorBox availability check failed; existing health statuses were preserved.",
        ) from error
    return _health_check_response(result)


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


@router.get("/diagnostics", response_model=LibraryDiagnosticsResponse)
async def library_diagnostics(
    library_root: Annotated[Path, Depends(get_library_root)],
) -> LibraryDiagnosticsResponse:
    report = await _validate_library(library_root)
    return LibraryDiagnosticsResponse(
        configured=True,
        root=str(report.summary.root),
        exists=report.summary.exists,
        ok=report.ok,
        total_files=report.summary.total_files,
        category_counts=report.summary.category_counts,
        warnings=[_issue_response(issue) for issue in report.warnings],
        errors=[_issue_response(issue) for issue in report.errors],
        duplicate_groups=[_duplicate_response(group) for group in report.summary.duplicate_groups],
        duplicate_file_count=sum(len(group.files) for group in report.summary.duplicate_groups),
    )


@router.get("/poster")
async def library_poster(
    media_item_id: Annotated[int, Query(ge=1)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    library_root: Annotated[Path, Depends(get_library_root)],
) -> FileResponse:
    record = await MediaMetadataRepository(session).find_for_media_item(media_item_id)
    await session.close()
    if record is None or record.tmdb_id is None:
        raise HTTPException(status_code=404, detail="Poster not found.")
    try:
        poster = poster_for_tmdb_id(library_root, record.tmdb_id)
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
    override = await save_media_classification(
        session,
        media_item_id=request.media_item_id,
        target_category=request.target_category,
    )
    await session.commit()
    return _classification_override_response(override)


@router.delete("/classification-overrides", status_code=204)
async def delete_classification_override(
    request: ClassificationOverrideDeleteRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    await delete_media_classification(session, request.media_item_id)
    await session.commit()


@router.delete("/entries", response_model=LibraryRemoveResponse)
async def remove_library_entry(
    request: LibraryRemoveRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    library_root: Annotated[Path, Depends(get_library_root)],
) -> LibraryRemoveResponse:
    if request.media_item_id is not None:
        location = await require_media_location(session, request.media_item_id)
        category = location.category
        title = location.title
        relative_path = location.relative_prefix
    else:
        _validate_relative_prefix(request.relative_path, request.category)
        category = request.category
        title = request.title
        relative_path = request.relative_path
    settings = get_settings()
    torbox_api_key = await effective_torbox_key(session, settings)
    if request.remove_torbox and torbox_api_key is None:
        raise HTTPException(status_code=400, detail="TorBox API key is not configured.")

    repository = LibraryExclusionRepository(session)
    backing_items = ()
    if request.remove_torbox:
        backing_items = (
            await repository.backing_items_for_media(request.media_item_id)
            if request.media_item_id is not None
            else await repository.backing_items(relative_path)
        )
    removal = await remove_library_media(
        session,
        library_root=library_root,
        category=category,
        title=title,
        relative_prefix=relative_path,
        backing_items=backing_items,
        torbox=(
            TorBoxRemovalConfig(
                api_key=torbox_api_key or "",
                base_url=settings.torbox_base_url,
                timeout=settings.outbound_timeout_seconds,
            )
            if request.remove_torbox
            else None
        ),
        client_factory=TorBoxClient,
    )
    action_message = (
        "Library entry removed. One or more TorBox deletions could not be confirmed."
        if removal.torbox_removal_failed
        else "Library entry removed."
    )
    auto_sync = await auto_sync_after_action(
        session=session,
        settings=settings,
        action_message=action_message,
    )
    return LibraryRemoveResponse(
        ok=True,
        message=auto_sync.message,
        removed_files=removal.removed_files,
        removed_torbox_items=removal.removed_torbox_items,
        torbox_removal_failed=removal.torbox_removal_failed,
        auto_sync_status=auto_sync.status,
        auto_sync_run_id=auto_sync.sync_run_id,
    )


@router.post("/entries/refresh-metadata", response_model=LibraryMetadataRefreshResponse)
async def refresh_entry_metadata(
    request: LibraryMetadataRefreshRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    library_root: Annotated[Path, Depends(get_library_root)],
) -> LibraryMetadataRefreshResponse:
    _validate_relative_prefix(request.relative_path, request.category)
    _ = await require_matching_media_record(
        session,
        media_item_id=request.media_item_id,
        relative_prefix=request.relative_path,
    )
    settings = get_settings()
    tmdb_api_key = await effective_tmdb_key(session, settings)
    if tmdb_api_key is None:
        raise HTTPException(status_code=400, detail="TMDB API key is not configured.")
    try:
        refreshed_posters = await refresh_tmdb_metadata(
            session,
            settings,
            library_root=library_root,
            media_item_id=request.media_item_id,
            tmdb_api_key=tmdb_api_key,
        )
    except MetadataRefreshError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (OSError, TmdbClientError, TmdbPosterError, ValueError) as error:
        raise HTTPException(status_code=503, detail="TMDB metadata refresh failed.") from error
    await session.commit()
    return LibraryMetadataRefreshResponse(
        ok=True,
        message="Metadata and poster refreshed.",
        refreshed_posters=refreshed_posters,
    )


@router.put("/entries/tmdb-id", response_model=LibraryTmdbIdUpdateResponse)
async def update_entry_tmdb_id(
    request: LibraryTmdbIdUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    library_root: Annotated[Path, Depends(get_library_root)],
) -> LibraryTmdbIdUpdateResponse:
    _validate_relative_prefix(request.relative_path, request.category)
    _ = await require_matching_media_record(
        session,
        media_item_id=request.media_item_id,
        relative_prefix=request.relative_path,
    )
    settings = get_settings()
    tmdb_api_key = await effective_tmdb_key(session, settings)
    if tmdb_api_key is None:
        raise HTTPException(status_code=400, detail="TMDB API key is not configured.")
    try:
        record = await MediaMetadataRepository(session).set_tmdb_id_for_media_item(
            request.media_item_id,
            str(request.tmdb_id),
        )
    except AuthoritativeIdentityConflictError as error:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    if record is None:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Library entry has no unique media record.",
        )

    try:
        refreshed_posters = await refresh_tmdb_metadata(
            session,
            settings,
            library_root=library_root,
            media_item_id=record.media_item.id,
            tmdb_api_key=tmdb_api_key,
        )
    except MetadataRefreshError as error:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (OSError, TmdbClientError, TmdbPosterError, ValueError) as error:
        await session.rollback()
        raise HTTPException(status_code=503, detail="TMDB metadata refresh failed.") from error

    await session.commit()
    return LibraryTmdbIdUpdateResponse(
        ok=True,
        message="TMDB ID, metadata, and artwork updated.",
        tmdb_id=request.tmdb_id,
        refreshed_posters=refreshed_posters,
    )


def _duplicate_response(group: LibraryDuplicateGroup) -> LibraryDuplicateGroupResponse:
    return LibraryDuplicateGroupResponse(
        key=group.key,
        files=[_file_response(file) for file in group.files],
    )


def _entry_response(
    entry: LibraryEntrySummary,
    record: LibraryMediaRecord | None,
    library_root: Path,
) -> LibraryEntryResponse:
    tmdb_id = record.tmdb_id if record is not None else None
    valid_tmdb_id = tmdb_id if tmdb_id is not None and tmdb_id.isdecimal() else None
    poster_url = None
    if (
        record is not None
        and valid_tmdb_id is not None
        and poster_for_tmdb_id(library_root, valid_tmdb_id) is not None
    ):
        poster_url = f"/api/library/poster?media_item_id={record.media_item.id}"
    return LibraryEntryResponse(
        key=entry.key,
        category=entry.category,
        title=entry.title,
        relative_path=entry.relative_path,
        file_count=entry.file_count,
        poster_url=poster_url,
        tmdb_id=int(valid_tmdb_id) if valid_tmdb_id is not None else None,
        media_item_id=record.media_item.id if record is not None else None,
        health=_unknown_health(entry.file_count),
    )


def _page_entry_response(
    entry: LibraryPageEntry,
    library_root: Path,
    health: LibraryHealthAggregate | None,
) -> LibraryEntryResponse:
    valid_tmdb_id = entry.tmdb_id if entry.tmdb_id and entry.tmdb_id.isdecimal() else None
    poster_url = None
    if valid_tmdb_id and poster_for_tmdb_id(library_root, valid_tmdb_id) is not None:
        poster_url = f"/api/library/poster?media_item_id={entry.media_item_id}"
    return LibraryEntryResponse(
        key=entry.relative_prefix,
        category=entry.category,
        title=entry.title,
        relative_path=entry.relative_prefix,
        file_count=entry.file_count,
        poster_url=poster_url,
        tmdb_id=int(valid_tmdb_id) if valid_tmdb_id else None,
        media_item_id=entry.media_item_id,
        health=_health_response(health, entry.file_count),
    )


def _health_response(
    health: LibraryHealthAggregate | None,
    file_count: int,
) -> LibraryHealthSummaryResponse:
    if health is None:
        return _unknown_health(file_count)
    return LibraryHealthSummaryResponse(
        status=health.status,
        total=health.total,
        ready=health.ready,
        recoverable=health.recoverable,
        unavailable=health.unavailable,
        unknown=health.unknown,
        checked_at=health.checked_at,
    )


def _unknown_health(file_count: int) -> LibraryHealthSummaryResponse:
    return LibraryHealthSummaryResponse(
        status="unknown",
        total=file_count,
        ready=0,
        recoverable=0,
        unavailable=0,
        unknown=file_count,
        checked_at=None,
    )


def _health_check_response(result: LibraryHealthCheckResult) -> LibraryHealthCheckResponse:
    return LibraryHealthCheckResponse(
        checked_at=result.checked_at,
        checked_entries=result.checked_entries,
        distinct_hashes=result.distinct_hashes,
        ready=result.ready,
        recoverable=result.recoverable,
        unavailable=result.unavailable,
        unknown=result.unknown,
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


async def _entry_records(
    session: AsyncSession | None,
    entries: tuple[LibraryEntrySummary, ...],
) -> dict[str, LibraryMediaRecord]:
    if session is None:
        return {}
    return await MediaMetadataRepository(session).records_for_library_prefixes(
        {entry.relative_path for entry in entries}
    )


async def _validate_library(library_root: Path) -> LibraryValidationReport:
    return validate_jellyfin_library(library_root)


def _validate_relative_prefix(relative_path: str, category: str) -> None:
    normalized = Path(relative_path)
    if normalized.is_absolute() or ".." in normalized.parts:
        raise HTTPException(status_code=400, detail="Library entry path is invalid.")
    if not relative_path.startswith(f"{category}/"):
        raise HTTPException(status_code=400, detail="Library entry category does not match path.")
