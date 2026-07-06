from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.library.paths import ensure_within_root


@dataclass(frozen=True, slots=True)
class LibraryRemovalResult:
    removed_files: int


def remove_library_prefix(library_root: Path, relative_prefix: str) -> LibraryRemovalResult:
    root = library_root.resolve(strict=False)
    target = ensure_within_root(root, root / relative_prefix)
    removed_files = 0

    if target.is_file() and target.suffix == ".strm":
        target.unlink()
        removed_files += 1
        _remove_empty_parents(root, target.parent)
        return LibraryRemovalResult(removed_files=removed_files)

    if not target.exists() or not target.is_dir():
        return LibraryRemovalResult(removed_files=0)

    for path in sorted(target.rglob("*.strm"), reverse=True):
        safe_path = ensure_within_root(root, path)
        safe_path.unlink()
        removed_files += 1
        _remove_empty_parents(root, safe_path.parent)

    _remove_empty_parents(root, target)
    return LibraryRemovalResult(removed_files=removed_files)


def _remove_empty_parents(root: Path, start: Path) -> None:
    current = ensure_within_root(root, start)
    while current != root and current.exists():
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent
