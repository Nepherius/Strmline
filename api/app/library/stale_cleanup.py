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


def _remove_empty_dirs(category_root: Path, safe_root: Path) -> None:
    for path in sorted(category_root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        safe_path = ensure_within_root(safe_root, path)
        if not safe_path.is_dir():
            continue
        try:
            safe_path.rmdir()
        except OSError:
            continue
