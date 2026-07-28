from pathlib import Path

from app.library.mutation_journal import LibraryMutationJournal


def test_mutation_journal_restores_only_tracked_files(tmp_path: Path) -> None:
    changed = tmp_path / "shows" / "Show" / "Show - S01E01.strm"
    unchanged = tmp_path / "movies" / "Movie" / "Movie.strm"
    changed.parent.mkdir(parents=True)
    unchanged.parent.mkdir(parents=True)
    _ = changed.write_text("original\n", encoding="utf-8")
    _ = unchanged.write_text("untouched\n", encoding="utf-8")
    journal = LibraryMutationJournal.create(tmp_path)
    journal.track(changed)

    _ = changed.write_text("changed\n", encoding="utf-8")
    _ = unchanged.write_text("external change\n", encoding="utf-8")
    new_file = tmp_path / "shows" / "Show" / "Show - S01E02.strm"
    journal.track(new_file)
    _ = new_file.write_text("new\n", encoding="utf-8")

    journal.restore()

    assert changed.read_text(encoding="utf-8") == "original\n"
    assert unchanged.read_text(encoding="utf-8") == "external change\n"
    assert new_file.exists() is False
