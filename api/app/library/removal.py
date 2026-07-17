from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.library.paths import ensure_within_root


@dataclass(frozen=True, slots=True)
class LibraryRemovalResult:
    removed_files: int


@dataclass(slots=True)
class StagedLibraryRemoval:
    root: Path
    target: Path
    quarantine: Path | None
    removed_files: int

    def restore(self) -> None:
        if self.quarantine is None or not self.quarantine.exists():
            return
        self.target.parent.mkdir(parents=True, exist_ok=True)
        if self.target.exists():
            msg = f"Cannot restore library removal because {self.target} already exists."
            raise FileExistsError(msg)
        _ = self.quarantine.replace(self.target)
        _remove_empty_parents(self.root, self.quarantine.parent)

    def finalize(self) -> LibraryRemovalResult:
        if self.quarantine is not None:
            operation_root = self.quarantine.parent
            if operation_root.exists():
                shutil.rmtree(operation_root)
            _remove_empty_parents(self.root, operation_root.parent)
        return LibraryRemovalResult(removed_files=self.removed_files)


def stage_library_prefix_removal(
    library_root: Path,
    relative_prefix: str,
) -> StagedLibraryRemoval:
    root = library_root.resolve(strict=False)
    target = ensure_within_root(root, root / relative_prefix)
    if not target.exists() or (target.is_file() and target.suffix != ".strm"):
        return StagedLibraryRemoval(root, target, None, 0)

    removed_files = 1 if target.is_file() else sum(1 for _ in target.rglob("*.strm"))
    operation_root = ensure_within_root(
        root,
        root / ".strmline" / "removal_quarantine" / uuid4().hex,
    )
    quarantine = operation_root / "payload"
    quarantine.parent.mkdir(parents=True, exist_ok=False)
    _ = target.replace(quarantine)
    _remove_empty_parents(root, target.parent)
    return StagedLibraryRemoval(root, target, quarantine, removed_files)


def remove_library_prefix(library_root: Path, relative_prefix: str) -> LibraryRemovalResult:
    return stage_library_prefix_removal(library_root, relative_prefix).finalize()


def _remove_empty_parents(root: Path, start: Path) -> None:
    current = ensure_within_root(root, start)
    while current != root and current.exists():
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent
