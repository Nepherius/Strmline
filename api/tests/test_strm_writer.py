from pathlib import Path

from app.library.entries import LibraryEntry
from app.library.strm_writer import write_strm_file


def test_write_strm_file_creates_parent_folders_and_file(tmp_path: Path):
    entry = LibraryEntry(
        category="movies",
        title="Exit 8",
        year=2025,
        resolver_url="http://strmline:8080/play/entry-id?token=secret",
    )

    written_path = write_strm_file(tmp_path, entry)

    assert written_path.exists()
    assert written_path.read_text(encoding="utf-8") == f"{entry.resolver_url}\n"
    assert written_path.relative_to(tmp_path).parts == (
        "movies",
        "Exit 8 (2025)",
        "Exit 8 (2025).strm",
    )


def test_write_strm_file_avoids_rewriting_unchanged_content(tmp_path: Path):
    entry = LibraryEntry(
        category="movies",
        title="Always",
        resolver_url="http://strmline:8080/play/always?token=secret",
    )

    first_path = write_strm_file(tmp_path, entry)
    first_stat = first_path.stat()

    second_path = write_strm_file(tmp_path, entry)

    assert second_path == first_path
    assert second_path.stat().st_mtime_ns == first_stat.st_mtime_ns
