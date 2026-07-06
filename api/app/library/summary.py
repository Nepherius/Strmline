from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from app.library.paths import ensure_within_root

LIBRARY_CATEGORIES = ("movies", "shows", "anime")
MIN_TITLE_PARTS = 2
TITLE_SEPARATORS = str.maketrans({".": " ", "_": " ", "(": " ", ")": " "})
EPISODE_SUFFIX = re.compile(r"(?i)\bs\d{1,2}e\d{1,3}\b")


@dataclass(frozen=True, slots=True)
class LibraryFile:
    category: str
    title: str
    relative_path: str
    duplicate_key: str


@dataclass(frozen=True, slots=True)
class LibraryDuplicateGroup:
    key: str
    files: tuple[LibraryFile, ...]


@dataclass(frozen=True, slots=True)
class LibraryEntrySummary:
    key: str
    category: str
    title: str
    relative_path: str
    file_count: int


@dataclass(frozen=True, slots=True)
class LibrarySummary:
    root: Path
    exists: bool
    total_files: int
    category_counts: dict[str, int]
    files: tuple[LibraryFile, ...]
    entries: tuple[LibraryEntrySummary, ...]
    duplicate_groups: tuple[LibraryDuplicateGroup, ...]


def summarize_library(root: Path) -> LibrarySummary:
    safe_root = root.resolve(strict=False)
    if not safe_root.exists():
        return _empty_summary(safe_root, exists=False)

    files = tuple(_iter_library_files(safe_root))
    return LibrarySummary(
        root=safe_root,
        exists=True,
        total_files=len(files),
        category_counts=_category_counts(files),
        files=files,
        entries=_entries(files),
        duplicate_groups=_duplicate_groups(files),
    )


def _empty_summary(root: Path, *, exists: bool) -> LibrarySummary:
    category_counts: dict[str, int] = dict.fromkeys(LIBRARY_CATEGORIES, 0)
    return LibrarySummary(
        root=root,
        exists=exists,
        total_files=0,
        category_counts=category_counts,
        files=(),
        entries=(),
        duplicate_groups=(),
    )


def _iter_library_files(root: Path) -> list[LibraryFile]:
    files: list[LibraryFile] = []
    for category in LIBRARY_CATEGORIES:
        category_root = ensure_within_root(root, root / category)
        if not category_root.exists():
            continue
        for path in sorted(category_root.rglob("*.strm")):
            safe_path = ensure_within_root(root, path)
            files.append(_library_file(root, safe_path, category))
    return files


def _library_file(root: Path, path: Path, category: str) -> LibraryFile:
    relative_path = path.relative_to(root).as_posix()
    title = _title_from_path(root, path, category)
    return LibraryFile(
        category=category,
        title=title,
        relative_path=relative_path,
        duplicate_key=_duplicate_key(category, title, path),
    )


def _title_from_path(root: Path, path: Path, category: str) -> str:
    relative = path.relative_to(root)
    parts = relative.parts
    if category == "movies" and len(parts) >= MIN_TITLE_PARTS:
        return parts[1]
    if category in {"shows", "anime"} and len(parts) >= MIN_TITLE_PARTS:
        return parts[1]
    return path.stem


def _normalized_title(value: str) -> str:
    return " ".join(value.casefold().translate(TITLE_SEPARATORS).split())


def _duplicate_key(category: str, title: str, path: Path) -> str:
    title_key = _normalized_title(title)
    if category == "movies":
        return f"{category}:{title_key}"
    episode_match = EPISODE_SUFFIX.search(path.stem)
    if episode_match is None:
        return f"{category}:{title_key}:{_normalized_title(path.stem)}"
    return f"{category}:{title_key}:{episode_match.group(0).casefold()}"


def _category_counts(files: tuple[LibraryFile, ...]) -> dict[str, int]:
    counts: dict[str, int] = dict.fromkeys(LIBRARY_CATEGORIES, 0)
    for file in files:
        counts[file.category] += 1
    return counts


def _entries(files: tuple[LibraryFile, ...]) -> tuple[LibraryEntrySummary, ...]:
    grouped: dict[str, list[LibraryFile]] = defaultdict(list)
    for file in files:
        grouped[_entry_key(file)].append(file)
    return tuple(
        _entry_summary(key, group)
        for key, group in sorted(grouped.items(), key=lambda item: item[0])
    )


def _entry_key(file: LibraryFile) -> str:
    parts = Path(file.relative_path).parts
    if len(parts) >= MIN_TITLE_PARTS:
        return "/".join(parts[:MIN_TITLE_PARTS])
    return file.relative_path


def _entry_summary(key: str, files: list[LibraryFile]) -> LibraryEntrySummary:
    first = files[0]
    return LibraryEntrySummary(
        key=key,
        category=first.category,
        title=first.title,
        relative_path=key,
        file_count=len(files),
    )


def _duplicate_groups(files: tuple[LibraryFile, ...]) -> tuple[LibraryDuplicateGroup, ...]:
    grouped: dict[str, list[LibraryFile]] = defaultdict(list)
    for file in files:
        grouped[file.duplicate_key].append(file)
    return tuple(
        LibraryDuplicateGroup(key=key, files=tuple(group))
        for key, group in sorted(grouped.items())
        if len(group) > 1
    )
