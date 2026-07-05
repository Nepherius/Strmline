from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.library.summary import LIBRARY_CATEGORIES, LibrarySummary, summarize_library

HTTP_URL = re.compile(r"^https?://", re.IGNORECASE)
SEASON_FOLDER = re.compile(r"^Season \d{2}$")
EPISODE_SUFFIX = re.compile(r"(?i)\bS\d{2}E\d{2,3}\b")
MOVIE_PATH_PARTS = 3
SERIES_PATH_PARTS = 4


@dataclass(frozen=True, slots=True)
class LibraryValidationIssue:
    code: str
    message: str
    relative_path: str | None = None


@dataclass(frozen=True, slots=True)
class LibraryValidationReport:
    summary: LibrarySummary
    warnings: tuple[LibraryValidationIssue, ...]
    errors: tuple[LibraryValidationIssue, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_jellyfin_library(root: Path) -> LibraryValidationReport:
    summary = summarize_library(root)
    warnings: list[LibraryValidationIssue] = []
    errors: list[LibraryValidationIssue] = []

    if not summary.exists:
        errors.append(
            LibraryValidationIssue(
                code="library_root_missing",
                message="Library root does not exist.",
            )
        )
        return LibraryValidationReport(summary=summary, warnings=(), errors=tuple(errors))

    _add_category_warnings(summary, warnings)
    errors.extend(_strm_files_outside_categories(summary.root))
    errors.extend(_invalid_strm_files(summary.root))
    warnings.extend(_duplicate_warnings(summary))
    return LibraryValidationReport(
        summary=summary,
        warnings=tuple(warnings),
        errors=tuple(errors),
    )


def _add_category_warnings(
    summary: LibrarySummary,
    warnings: list[LibraryValidationIssue],
) -> None:
    if summary.total_files == 0:
        warnings.append(
            LibraryValidationIssue(
                code="library_empty",
                message="No STRM files were found. Run a sync before adding libraries in Jellyfin.",
            )
        )


def _strm_files_outside_categories(root: Path) -> list[LibraryValidationIssue]:
    issues: list[LibraryValidationIssue] = []
    for path in sorted(root.rglob("*.strm")):
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] in LIBRARY_CATEGORIES:
            continue
        issues.append(
            LibraryValidationIssue(
                code="strm_outside_category",
                message="STRM file is outside movies, shows, or anime.",
                relative_path=relative.as_posix(),
            )
        )
    return issues


def _invalid_strm_files(root: Path) -> list[LibraryValidationIssue]:
    issues: list[LibraryValidationIssue] = []
    for category in LIBRARY_CATEGORIES:
        category_root = root / category
        if not category_root.exists():
            continue
        for path in sorted(category_root.rglob("*.strm")):
            relative = path.relative_to(root)
            issue = _validate_strm_file(path, relative, category)
            if issue is not None:
                issues.append(issue)
    return issues


def _validate_strm_file(
    path: Path,
    relative: Path,
    category: str,
) -> LibraryValidationIssue | None:
    content = path.read_text(encoding="utf-8").strip()
    relative_path = relative.as_posix()
    if not content:
        return LibraryValidationIssue("strm_empty", "STRM file is empty.", relative_path)
    if "\n" in content:
        return LibraryValidationIssue(
            "strm_multiple_lines",
            "STRM file should contain one playback URL.",
            relative_path,
        )
    if HTTP_URL.search(content) is None:
        return LibraryValidationIssue(
            "strm_url_invalid",
            "STRM playback URL must start with http:// or https://.",
            relative_path,
        )
    return _validate_relative_shape(relative, category)


def _validate_relative_shape(relative: Path, category: str) -> LibraryValidationIssue | None:
    parts = relative.parts
    relative_path = relative.as_posix()
    if category == "movies" and len(parts) != MOVIE_PATH_PARTS:
        return LibraryValidationIssue(
            "movie_path_shape",
            "Movie STRM files should be under movies/Title/Title.strm.",
            relative_path,
        )
    if category == "shows":
        return _validate_series_shape(parts, relative_path, category_name="Show")
    if category == "anime" and len(parts) == MOVIE_PATH_PARTS:
        return None
    if category == "anime":
        return _validate_series_shape(parts, relative_path, category_name="Anime series")
    return None


def _validate_series_shape(
    parts: tuple[str, ...],
    relative_path: str,
    *,
    category_name: str,
) -> LibraryValidationIssue | None:
    if len(parts) != SERIES_PATH_PARTS:
        return LibraryValidationIssue(
            "series_path_shape",
            f"{category_name} STRM files should be under category/Title/Season XX/Title - SXXEYY.strm.",
            relative_path,
        )
    if SEASON_FOLDER.fullmatch(parts[2]) is None:
        return LibraryValidationIssue(
            "season_folder_shape",
            "Season folder should use the format Season 01.",
            relative_path,
        )
    if EPISODE_SUFFIX.search(Path(parts[3]).stem) is None:
        return LibraryValidationIssue(
            "episode_filename_shape",
            "Episode filename should include SXXEYY.",
            relative_path,
        )
    return None


def _duplicate_warnings(summary: LibrarySummary) -> list[LibraryValidationIssue]:
    return [
        LibraryValidationIssue(
            code="duplicate_generated_path",
            message=f"Duplicate generated entry group contains {len(group.files)} files.",
            relative_path=group.files[0].relative_path,
        )
        for group in summary.duplicate_groups
    ]
