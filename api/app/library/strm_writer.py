from __future__ import annotations

from pathlib import Path

from app.library.entries import LibraryEntry
from app.library.paths import ensure_within_root, library_entry_relative_path


def write_strm_file(library_root: Path, entry: LibraryEntry) -> Path:
    relative_path = library_entry_relative_path(entry)
    target_path = ensure_within_root(library_root, library_root / relative_path)
    content = f"{entry.resolver_url}\n"

    if target_path.exists() and target_path.read_text(encoding="utf-8") == content:
        return target_path

    target_path.parent.mkdir(parents=True, exist_ok=True)
    _ = target_path.write_text(content, encoding="utf-8")
    return target_path
