from pathlib import Path

from app.library.sync_snapshot import LibrarySyncSnapshot
from app.resolver.manifest import MANIFEST_RELATIVE_PATH


def test_sync_snapshot_restores_changed_and_new_generated_files(tmp_path: Path) -> None:
    existing = tmp_path / "shows" / "Show" / "Show - S01E01.strm"
    existing.parent.mkdir(parents=True)
    _ = existing.write_text("original\n", encoding="utf-8")
    manifest = tmp_path / MANIFEST_RELATIVE_PATH
    manifest.parent.mkdir(parents=True)
    _ = manifest.write_text('{"version": 1, "entries": {}}\n', encoding="utf-8")
    snapshot = LibrarySyncSnapshot.capture(tmp_path)

    _ = existing.write_text("changed\n", encoding="utf-8")
    new_file = tmp_path / "shows" / "Show" / "Show - S01E02.strm"
    _ = new_file.write_text("new\n", encoding="utf-8")
    _ = manifest.write_text(
        '{"version": 1, "entries": {"new": "url"}}\n',
        encoding="utf-8",
    )

    snapshot.restore()

    assert existing.read_text(encoding="utf-8") == "original\n"
    assert new_file.exists() is False
    assert manifest.read_text(encoding="utf-8") == '{"version": 1, "entries": {}}\n'


def test_sync_snapshot_removes_manifest_created_by_failed_sync(tmp_path: Path) -> None:
    snapshot = LibrarySyncSnapshot.capture(tmp_path)
    manifest = tmp_path / MANIFEST_RELATIVE_PATH
    manifest.parent.mkdir(parents=True)
    _ = manifest.write_text('{"version": 1, "entries": {}}\n', encoding="utf-8")

    snapshot.restore()

    assert manifest.exists() is False
