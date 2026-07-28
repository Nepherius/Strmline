from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.library.atomic_io import atomic_write_bytes
from app.library.paths import ensure_within_root


@dataclass(slots=True)
class LibraryMutationJournal:
    """Capture only files a sync is about to mutate so they can be restored."""

    root: Path
    _originals: dict[Path, bytes | None]

    @classmethod
    def create(cls, library_root: Path) -> LibraryMutationJournal:
        return cls(root=library_root.resolve(strict=False), _originals={})

    def track(self, path: Path) -> None:
        safe_path = ensure_within_root(self.root, path)
        relative_path = safe_path.relative_to(self.root)
        if relative_path in self._originals:
            return
        self._originals[relative_path] = safe_path.read_bytes() if safe_path.is_file() else None

    def restore(self) -> None:
        for relative_path, content in self._originals.items():
            path = ensure_within_root(self.root, self.root / relative_path)
            if content is None:
                _ = path.unlink(missing_ok=True)
                _remove_empty_parents(self.root, path.parent)
                continue
            atomic_write_bytes(path, content)


def _remove_empty_parents(root: Path, start: Path) -> None:
    current = ensure_within_root(root, start)
    while current != root and current.exists():
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent
