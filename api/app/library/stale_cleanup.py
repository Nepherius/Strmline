from __future__ import annotations

from pathlib import Path

from app.library.paths import ensure_within_root

GENERATED_CATEGORY_DIRS = ("movies", "shows", "anime")


def remove_stale_strm_files(library_root: Path, current_paths: set[Path]) -> None:
    safe_root = library_root.resolve(strict=False)
    current_resolved = {path.resolve(strict=False) for path in current_paths}
    for category in GENERATED_CATEGORY_DIRS:
        category_root = ensure_within_root(safe_root, safe_root / category)
        if not category_root.exists():
            continue
        for path in category_root.rglob("*.strm"):
            safe_path = ensure_within_root(safe_root, path)
            if safe_path in current_resolved:
                continue
            safe_path.unlink()
        _remove_empty_dirs(category_root, safe_root)


def remove_stale_strm_paths(library_root: Path, stale_paths: set[Path]) -> None:
    """Remove exact generated paths already identified as stale by persistence."""
    safe_root = library_root.resolve(strict=False)
    touched_directories: set[Path] = set()
    for path in stale_paths:
        safe_path = ensure_within_root(safe_root, path)
        if safe_path.suffix.casefold() != ".strm":
            continue
        _ = safe_path.unlink(missing_ok=True)
        touched_directories.add(safe_path.parent)
    for directory in sorted(touched_directories, key=lambda item: len(item.parts), reverse=True):
        _remove_empty_parents(directory, safe_root)


def _remove_empty_dirs(category_root: Path, safe_root: Path) -> None:
    for path in sorted(category_root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        safe_path = ensure_within_root(safe_root, path)
        if not safe_path.is_dir():
            continue
        try:
            safe_path.rmdir()
        except OSError:
            continue


def _remove_empty_parents(start: Path, safe_root: Path) -> None:
    current = ensure_within_root(safe_root, start)
    while current != safe_root and current.exists():
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent
