from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.library.atomic_io import atomic_write_bytes
from app.library.paths import ensure_within_root
from app.resolver.manifest import MANIFEST_RELATIVE_PATH


@dataclass(frozen=True, slots=True)
class LibrarySyncSnapshot:
    """Restorable generated-library state captured before a synchronization pass."""

    root: Path
    files: dict[Path, bytes]

    @classmethod
    def capture(cls, library_root: Path) -> LibrarySyncSnapshot:
        root = library_root.resolve(strict=False)
        paths: set[Path] = set(root.rglob("*.strm")) if root.exists() else set()
        manifest = ensure_within_root(root, root / MANIFEST_RELATIVE_PATH)
        if manifest.is_file():
            paths.add(manifest)
        return cls(
            root=root,
            files={
                path.relative_to(root): path.read_bytes()
                for path in paths
                if path.is_file()
            },
        )

    def restore(self) -> None:
        current: set[Path] = (
            set(self.root.rglob("*.strm")) if self.root.exists() else set()
        )
        manifest = ensure_within_root(self.root, self.root / MANIFEST_RELATIVE_PATH)
        if manifest.is_file():
            current.add(manifest)

        expected = {ensure_within_root(self.root, self.root / path) for path in self.files}
        for path in current - expected:
            _ = path.unlink(missing_ok=True)
            _remove_empty_parents(self.root, path.parent)
        for relative_path, content in self.files.items():
            atomic_write_bytes(
                ensure_within_root(self.root, self.root / relative_path),
                content,
            )


def _remove_empty_parents(root: Path, start: Path) -> None:
    current = ensure_within_root(root, start)
    while current != root and current.exists():
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent
